"""Activation coordination uses isolated user roots and real OS endpoints."""

import json
import socket
import subprocess
import sys
from pathlib import Path
from threading import Event


def test_second_launch_requests_activation_without_creating_another_owner(tmp_path):
    from brz2obsidian_ui.instance import LocalInstance

    activated = Event()
    first = LocalInstance(tmp_path, activated.set)
    try:
        assert first.claim().status == "primary"
        second = LocalInstance(tmp_path, lambda: None)
        assert second.claim().status == "activation_requested"
        assert activated.wait(2)
        assert second.owns_endpoint is False
    finally:
        first.close()
    assert not (tmp_path / "instance.json").exists()


def test_real_second_process_activates_and_cli_is_independent(tmp_path):
    from brz2obsidian_ui.instance import LocalInstance

    activated = Event()
    first = LocalInstance(tmp_path, activated.set)
    try:
        assert first.claim().status == "primary"
        second = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path; import sys; "
                    "from brz2obsidian_ui.instance import LocalInstance; "
                    "print(LocalInstance(Path(sys.argv[1]), lambda: None).claim().status)"
                ),
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert second.returncode == 0
        assert second.stdout.strip() == "activation_requested"
        assert activated.wait(2)
        cli = subprocess.run(
            [sys.executable, "-m", "brz2obsidian", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert cli.returncode == 0
        assert "inspect" in cli.stdout
        inspected = subprocess.run(
            [
                sys.executable,
                "-m",
                "brz2obsidian",
                "inspect",
                str((Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
        assert inspected.returncode == 0
        assert "inspect: clean" in inspected.stdout
        assert first.owns_endpoint
    finally:
        first.close()


def test_crashed_owner_releases_lock_and_stale_registration_is_replaced(tmp_path):
    from brz2obsidian_ui.instance import LocalInstance

    # Crash the actual owner, not the venv's Windows redirector process.
    child = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            (
                "from pathlib import Path; import os, sys; "
                "from brz2obsidian_ui.instance import LocalInstance; "
                "owner = LocalInstance(Path(sys.argv[1]), lambda: None); "
                "print(owner.claim().status, flush=True); "
                "sys.stdin.readline(); os._exit(0)"
            ),
            str(tmp_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout.readline().strip() == "primary"
        previous = (tmp_path / "instance.json").read_bytes()
        child.stdin.write("crash\n")
        child.stdin.flush()
        child.wait(timeout=5)
        fresh = LocalInstance(tmp_path, lambda: None)
        try:
            assert fresh.claim().status == "primary"
            assert (tmp_path / "instance.json").read_bytes() != previous
        finally:
            fresh.close()
    finally:
        if child.poll() is None:
            child.stdin.close()
            child.wait(timeout=5)


def test_endpoint_rejects_work_paths_and_incorrect_authentication(tmp_path):
    from brz2obsidian_ui.instance import LocalInstance

    activated = Event()
    first = LocalInstance(tmp_path, activated.set)
    try:
        first.claim()
        endpoint = json.loads((tmp_path / "instance.json").read_text("utf-8"))
        for message in (
            b"activate incorrect\n",
            f"convert {endpoint['token']} C:/source.brz\n".encode(),
            f"activate {endpoint['token']} C:/source.brz\n".encode(),
        ):
            with socket.create_connection(("127.0.0.1", endpoint["port"]), 1) as conn:
                conn.sendall(message)
                conn.shutdown(socket.SHUT_WR)
                assert conn.recv(32) == b""
        assert not activated.is_set()
        assert first.owns_endpoint
    finally:
        first.close()


def test_live_owner_is_never_replaced_if_endpoint_is_unavailable(tmp_path):
    from brz2obsidian_ui.instance import LocalInstance

    first = LocalInstance(tmp_path, lambda: None)
    try:
        first.claim()
        (tmp_path / "instance.json").write_text("corrupt", "utf-8")
        second = LocalInstance(tmp_path, lambda: None)
        result = second.claim()
        assert result.status == "unavailable" and result.feedback
        assert first.owns_endpoint and not second.owns_endpoint
        assert (tmp_path / "instance.json").read_text("utf-8") == "corrupt"
    finally:
        first.close()


def test_foreground_denial_produces_attention_and_nonfatal_feedback():
    from brz2obsidian_ui.instance import WindowActivator

    class Windows:
        def restore(self, hwnd):
            assert hwnd == 42

        def foreground(self, hwnd):
            return False

        def attention(self, hwnd):
            self.attention_window = hwnd

    windows = Windows()
    result = WindowActivator(windows).activate(42)
    assert result.status == "attention_requested"
    assert result.feedback == "The app is already open. Select it from the taskbar."
    assert windows.attention_window == 42
