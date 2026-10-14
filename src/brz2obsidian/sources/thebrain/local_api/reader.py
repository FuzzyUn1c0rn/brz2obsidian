"""Read-only source composition and session lifetime."""

import os
import time
from contextlib import contextmanager
from contextvars import ContextVar

from brz2obsidian.contracts import MigrationFailed, MigrationRefused

from .acquisition import Acquisition
from .config import LocalApiConfig, LocalApiSourceRef
from .errors import failure, refuse
from .metadata import LocalApiRunMetadata
from .transport import LocalHttp


class LocalApiSourceModule:
    """Acquire afresh on every open using external credentials.

    Reads span multiple requests and are not atomic. The yielded session verifies
    the captured copy; it cannot prove live atomicity or universal discovery.
    Closing releases the capture, so conversion after inspection reacquires it.
    """

    def __init__(self, config=None, *, credentials=None, clock=None):
        self.config = config or LocalApiConfig()
        self.clock = clock or time.monotonic
        self.credentials = credentials or (
            lambda: os.environ.get("THE_BRAIN_LOCAL_API_KEY")
        )
        self._active_session = ContextVar("local_api_active_session", default=None)

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
                refuse("The local API credential provider is unavailable")
            client = LocalHttp(self.config, token, source_ref.brain_id, self.clock)
            session = Acquisition(
                client, self.config, source_ref.brain_id, self.clock
            ).acquire()
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
