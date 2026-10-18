"""Safe report lifetime and admission through the public host session."""

from pathlib import Path

from brz2obsidian.application.contracts import ApplyResult, InspectCommand, SelectSource
from brz2obsidian.application.operations import inspect

SOURCE = (Path(__file__).parents[1] / "fixtures/minimal.brz").absolute()


def complete_inspection(session, text="Safe report\n"):
    if session.snapshot.source is None:
        session.dispatch(SelectSource(path_or_null=str(SOURCE)))
    started = session.dispatch(InspectCommand()).effects[0]
    result = inspect(SOURCE).model_copy(update={"diagnostic_text": text})
    return session.dispatch(
        ApplyResult(
            request_id=started.request.request_id,
            input_revision=started.input_revision,
            result=result,
            process_status=0,
        )
    )
