# Type stubs for bb.process
import subprocess
from typing import IO, Any, Sequence

class CmdError(RuntimeError):
    command: str | Sequence[str]
    msg: str | None
    def __init__(self, command: str | Sequence[str], msg: str | None = ...) -> None: ...

class NotFoundError(CmdError): ...

class ExecutionError(CmdError):
    exitcode: int
    stdout: str | None
    stderr: str | None
    extra_message: str | None
    def __init__(self, command: str | Sequence[str], exitcode: int, stdout: str | None = ...,
                 stderr: str | None = ...) -> None: ...

class Popen(subprocess.Popen[Any]):
    defaults: dict[str, Any]
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

def run(cmd: str | Sequence[str], input: str | bytes | None = ..., log: IO[Any] | None = ...,
        extrafiles: list[tuple[IO[Any], Any]] | None = ..., **options: Any) -> tuple[str, str]: ...
