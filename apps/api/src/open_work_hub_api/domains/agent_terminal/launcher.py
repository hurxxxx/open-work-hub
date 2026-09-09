from __future__ import annotations

import ctypes
import os
import signal
import sys

_PR_SET_PDEATHSIG = 1


def _terminate_when_api_parent_exits() -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(_PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0) != 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))
    if os.getppid() == 1:
        raise RuntimeError("API parent exited before terminal launch")


def main(argv: list[str] | None = None) -> int:
    command = list(argv if argv is not None else sys.argv[1:])
    if not command:
        raise RuntimeError("Missing terminal command")
    _terminate_when_api_parent_exits()
    os.execve(command[0], command, dict(os.environ))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
