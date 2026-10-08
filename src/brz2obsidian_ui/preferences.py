"""Parent-only local preferences. Call these file operations off the Qt thread."""

import json
import ntpath
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


def application_data() -> Path | None:
    """Use Windows' user-local app-data area; never fall back to the checkout."""
    location = _absolute_directory(os.environ.get("LOCALAPPDATA"))
    return location / "brz2obsidian" if location is not None else None


def _absolute_directory(value: Path | str | None) -> Path | None:
    if value is None:
        return None
    try:
        path = Path(value)
    except TypeError, ValueError:
        return None
    if not path.is_absolute() or ntpath.isreserved(path):
        return None
    drive = path.drive
    if len(drive) == 2 and drive[1] == ":":
        if drive[0] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz":
            return None
    elif not drive.startswith("\\\\") or ":" in drive:
        return None
    if any(character in '<>|?"*' or ord(character) < 32 for character in drive):
        return None
    return path


@dataclass(frozen=True)
class PreferenceResult:
    parent: str | None = None
    feedback: str | None = None


class ParentPreferences:
    """The only persistent application preference is the last output parent."""

    def __init__(self, directory: Path | None):
        self.directory = _absolute_directory(directory)

    def load(self) -> PreferenceResult:
        if self.directory is None:
            return PreferenceResult(feedback="Output folder preference is unavailable.")
        try:
            if self.directory.exists() and not self.directory.is_dir():
                raise ValueError("Invalid preference directory")
            path = self.directory / "preferences.json"
            with path.open("rb") as stream:
                raw = stream.read(32769)
            if len(raw) > 32768:
                raise ValueError("Oversized preference")
            value = json.loads(raw.decode("utf-8"))
            if (
                not isinstance(value, dict)
                or set(value) != {"output_parent"}
                or not isinstance(value["output_parent"], str)
                or not Path(value["output_parent"]).is_absolute()
            ):
                raise ValueError("Invalid preference")
            return PreferenceResult(parent=value["output_parent"])
        except FileNotFoundError:
            return PreferenceResult()
        except OSError, ValueError, UnicodeError:
            return PreferenceResult(
                feedback="The saved output folder could not be read. Choose a folder."
            )

    def save(self, parent: str) -> PreferenceResult:
        temporary = None
        try:
            if self.directory is None or not Path(parent).is_absolute():
                raise ValueError("Unavailable preference location")
            self.directory.mkdir(parents=True, exist_ok=True)
            payload = json.dumps({"output_parent": parent}, ensure_ascii=False)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.directory, delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.directory / "preferences.json")
            return PreferenceResult(parent=parent)
        except OSError, ValueError:
            return PreferenceResult(
                feedback="The output folder could not be remembered for the next launch."
            )
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
