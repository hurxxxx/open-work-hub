from __future__ import annotations

import fcntl
import os
import sys
import termios


def main(argv: list[str] | None = None) -> int:
    """Exec tmux with the PTY as its controlling terminal for SIGWINCH delivery."""
    command = list(argv if argv is not None else sys.argv[1:])
    if not command:
        raise RuntimeError("Missing tmux client command")
    fcntl.ioctl(sys.stdin.fileno(), termios.TIOCSCTTY, 0)
    os.execve(command[0], command, dict(os.environ))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
