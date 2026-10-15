"""Read-only source composition and session lifetime."""

import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from brz2obsidian.contracts import MigrationFailed, MigrationRefused

from .acquisition import Acquisition
from .capture import identifiers
from .config import LocalApiConfig, LocalApiSourceRef
from .errors import failure, refuse
from .metadata import LocalApiRunMetadata
from .storage import acquisition_storage
from .transport import LocalHttp


@dataclass(frozen=True)
class AccessibleBrain:
    brain_id: str
    name: str


class LocalApiSourceModule:
    """Acquire afresh on every open using external credentials.

    Reads span multiple requests and are not atomic. The yielded session verifies
    the captured copy; it cannot prove live atomicity or universal discovery.
    Closing releases the capture, so conversion after inspection reacquires it.
    """

    def __init__(
        self, config=None, *, credentials=None, clock=None, profile_version="1"
    ):
        self.profile_version = identifiers(profile_version)["profile_version"]
        self.config = config or LocalApiConfig()
        self.clock = clock or time.monotonic
        self.credentials = credentials or (
            lambda: os.environ.get("THE_BRAIN_LOCAL_API_KEY")
        )
        self._active_session = ContextVar("local_api_active_session", default=None)

    def list_brains(self):
        """Bounded unscoped listing; no capture or invented Brain audit identity."""
        try:
            token = self.credentials()
            if not isinstance(token, str) or not token:
                raise failure(
                    "api_credentials_missing",
                    "The local API credential provider is unavailable",
                )
            client = LocalHttp(self.config, token, None, self.clock)
            rows = client.json("brain", "/brains")
            if (
                not isinstance(rows, list)
                or len(rows) > self.config.max_traversal_items
            ):
                refuse("Accessible Brain inventory is malformed or exceeds its bound")
            client.ensure_safe(rows)
            seen, result = set(), []
            for row in rows:
                if (
                    not isinstance(row, dict)
                    or not isinstance(row.get("name"), str)
                    or not row["name"].strip()
                ):
                    refuse("Accessible Brain metadata is malformed")
                brain_id = LocalApiSourceRef(row.get("id")).brain_id
                if brain_id in seen:
                    refuse("Accessible Brain identities conflict")
                seen.add(brain_id)
                result.append(AccessibleBrain(brain_id, row["name"]))
            return tuple(result)
        except MigrationFailed, MigrationRefused:
            raise
        except Exception:  # noqa: BLE001 -- never expose external provider or malformed input text.
            raise failure(
                "api_listing_failed", "Accessible Brains could not be listed safely"
            ) from None

    def run_metadata(self, metadata):
        session = self._active_session.get()
        if session is None or session.closed:
            raise failure(
                "api_acquisition_context_missing", "No frozen API acquisition is active"
            )
        return LocalApiRunMetadata(
            **metadata.model_dump(), source_acquisition=session.acquisition
        )

    @contextmanager
    def open(self, source_ref):
        try:
            if not isinstance(source_ref, LocalApiSourceRef):
                refuse("Select a canonical local API Brain reference")
            token = self.credentials()
            if not isinstance(token, str) or not token:
                raise failure(
                    "api_credentials_missing",
                    "The local API credential provider is unavailable",
                )
            client = LocalHttp(self.config, token, source_ref.brain_id, self.clock)
            session = None
            try:
                with acquisition_storage() as directory:
                    session = Acquisition(
                        client,
                        self.config,
                        source_ref.brain_id,
                        self.clock,
                        self.profile_version,
                        directory,
                    ).acquire()
            except BaseException:
                if session is not None:
                    session.close()
                raise
        except MigrationFailed, MigrationRefused:
            raise
        except Exception:  # noqa: BLE001 - external credential providers must not expose exception text.
            raise failure(
                "api_acquisition_failed",
                "Local API acquisition could not complete safely",
            ) from None
        active_token = self._active_session.set(session)
        try:
            yield session
        finally:
            try:
                session.close()
            finally:
                self._active_session.reset(active_token)
