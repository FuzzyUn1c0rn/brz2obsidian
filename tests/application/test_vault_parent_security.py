"""Independent Windows descriptor observations at the public staging seam."""

import ctypes
import json
import os
import shutil
import subprocess
import tempfile
from ctypes import wintypes
from pathlib import Path
from uuid import uuid4

import pytest

from brz2obsidian.publication.vault_replace import stage_parent_security

_ACL_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$observed = foreach ($path in (ConvertFrom-Json $env:BRZ280_SECURITY_PATHS)) {
    $acl = Get-Acl -LiteralPath $path
    $raw = [System.Security.AccessControl.RawSecurityDescriptor]::new(
        $acl.GetSecurityDescriptorBinaryForm(), 0)
    $aces = @(
        for ($index = 0; $index -lt $raw.DiscretionaryAcl.Count; $index++) {
            $ace = $raw.DiscretionaryAcl[$index]
            $bytes = [byte[]]::new($ace.BinaryLength)
            $ace.GetBinaryForm($bytes, 0)
            [Convert]::ToBase64String($bytes)
        }
    )
    [ordered]@{
        path = $path
        sddl = $acl.Sddl
        owner = $raw.Owner.Value
        group = $raw.Group.Value
        control = [int]$raw.ControlFlags
        protected = $acl.AreAccessRulesProtected
        ordered_aces = $aces
    }
}
ConvertTo-Json -InputObject @($observed) -Depth 8 -Compress
"""


def observe_acl(*paths):
    executable = shutil.which("pwsh") or shutil.which("powershell")
    assert executable is not None, "Windows ACL oracle requires PowerShell"
    output = subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-Command", _ACL_SCRIPT],
        env=os.environ
        | {"BRZ280_SECURITY_PATHS": json.dumps([str(path) for path in paths])},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=True,
    )
    return json.loads(output.stdout)


def seed_inherited_directory_acl(path):
    """Create the observed old child state independently of the production helper."""
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.DWORD),
    ]
    convert.restype = wintypes.BOOL
    apply = advapi.SetFileSecurityW
    apply.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
    apply.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    descriptor = ctypes.c_void_p()
    inherited = "D:(A;OICIID;FA;;;SY)(A;OICIID;FA;;;BA)(A;OICIID;FA;;;OW)"
    if not convert(inherited, 1, ctypes.byref(descriptor), None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not apply(str(path), 4, descriptor):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.LocalFree(descriptor)


@pytest.fixture
def security_case():
    container = Path(tempfile.mkdtemp(prefix="brz2obsidian-280-parent-security-"))
    source, stage = container / "source", container / "stage"
    source.mkdir(mode=0o700)
    stage.mkdir()
    (source / "ordinary.bin").write_bytes(b"literal source\x00\xff")
    record = {
        "owner": uuid4().hex,
        "root": str(container.resolve()),
        "base": str(Path(tempfile.gettempdir()).resolve()),
        "source": str(source),
        "stage": str(stage),
    }
    (container / ".fixture-owner.json").write_text(json.dumps(record), encoding="utf-8")
    evidence = (
        Path(__file__).resolve().parents[2]
        / "tmp/issue-280-parent-security/fixtures"
        / record["owner"]
    )
    evidence.mkdir(parents=True)
    (evidence / "owner.json").write_text(json.dumps(record), encoding="utf-8")
    return source, stage, evidence


@pytest.mark.skipif(os.name != "nt", reason="Windows security descriptor contract")
def test_staged_root_retains_protected_parent_descriptor_exactly(security_case):
    source, stage, evidence = security_case
    before = observe_acl(source, stage)
    (evidence / "before.json").write_text(json.dumps(before), encoding="utf-8")
    assert before[0]["protected"] is True
    assert before[0]["control"] & 0x0400 == 0
    assert "D:P(" in before[0]["sddl"]
    assert before[1]["protected"] is False
    assert len(before[0]["ordered_aces"]) == 3
    try:
        stage_parent_security(source, stage, Path("."))
    finally:
        after = observe_acl(source, stage)
        (evidence / "after.json").write_text(json.dumps(after), encoding="utf-8")
    assert after[0] == before[0]
    assert {k: v for k, v in after[1].items() if k != "path"} == {
        k: v for k, v in before[0].items() if k != "path"
    }
    assert (source / "ordinary.bin").read_bytes() == b"literal source\x00\xff"
    assert tuple(stage.iterdir()) == ()
    stage_parent_security(source, stage, Path("."))
    assert observe_acl(source, stage) == after


@pytest.mark.skipif(os.name != "nt", reason="Windows security descriptor contract")
def test_inherited_nested_parents_retain_exact_security_and_staged_bytes(security_case):
    source, stage, evidence = security_case
    relative = Path("parent/nested")
    (source / relative).mkdir(parents=True)
    seed_inherited_directory_acl(source / "parent")
    seed_inherited_directory_acl(source / relative)
    (source / relative / "source.bin").write_bytes(b"nested source\x00\xff")
    sources = (source, source / "parent", source / relative)
    before = observe_acl(*sources)
    (evidence / "nested-before.json").write_text(json.dumps(before), encoding="utf-8")
    assert before[1]["protected"] is False
    assert before[1]["control"] & 0x0400 == 0
    assert before[1]["sddl"].split("D:", 1)[1] == (
        "(A;OICIID;FA;;;SY)(A;OICIID;FA;;;BA)(A;OICIID;FA;;;OW)"
    )
    try:
        stage_parent_security(source, stage, relative)
    finally:
        paths = sources + tuple(stage / path.relative_to(source) for path in sources)
        observed = observe_acl(*(path for path in paths if path.exists()))
        (evidence / "nested-after.json").write_text(
            json.dumps(observed), encoding="utf-8"
        )
    assert observed[:3] == before
    for original, copied in zip(before, observed[3:], strict=True):
        assert {k: v for k, v in copied.items() if k != "path"} == {
            k: v for k, v in original.items() if k != "path"
        }
    staged_file = stage / relative / "staged.bin"
    staged_file.write_bytes(b"existing staged bytes\x00\xff")
    file_acl = observe_acl(staged_file)
    stage_parent_security(source, stage, relative)
    assert observe_acl(*paths) == observed
    assert observe_acl(staged_file) == file_acl
    assert staged_file.read_bytes() == b"existing staged bytes\x00\xff"
    assert (source / relative / "source.bin").read_bytes() == b"nested source\x00\xff"
    assert (source / "ordinary.bin").read_bytes() == b"literal source\x00\xff"


@pytest.mark.skipif(os.name != "nt", reason="Windows security descriptor contract")
def test_parent_security_refuses_a_different_group_without_changing_source(
    security_case,
):
    source, stage, evidence = security_case
    executable = shutil.which("pwsh") or shutil.which("powershell")
    script = r"""
$ErrorActionPreference = 'Stop'
$paths = @(ConvertFrom-Json $env:BRZ280_SECURITY_PATHS)
$path = $paths[0]
$acl = Get-Acl -LiteralPath $path
$acl.SetGroup([System.Security.Principal.SecurityIdentifier]::new('S-1-5-32-545'))
Set-Acl -LiteralPath $path -AclObject $acl
"""
    subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-Command", script],
        env=os.environ | {"BRZ280_SECURITY_PATHS": json.dumps([str(stage)])},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=True,
    )
    before = observe_acl(source, stage)
    assert before[1]["group"] == "S-1-5-32-545"
    assert before[0]["group"] != before[1]["group"]
    (evidence / "group-before.json").write_text(json.dumps(before), encoding="utf-8")
    with pytest.raises(OSError, match="owner, group or DACL changed"):
        stage_parent_security(source, stage, Path("."))
    after = observe_acl(source, stage)
    (evidence / "group-after.json").write_text(json.dumps(after), encoding="utf-8")
    assert after[0] == before[0]
    assert after[1]["group"] == before[1]["group"]
    assert (source / "ordinary.bin").read_bytes() == b"literal source\x00\xff"
    assert tuple(stage.iterdir()) == ()
