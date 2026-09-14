"""Kernel write boundary for native file-tool subprocesses inside the sandbox.

The native guard canonicalizes paths on the gateway, while the native shell
writer follows links in the sandbox. Landlock enforces the final filesystem
operation, including rename/delete and symlink races, without replacing the
upstream patch engine. Requires Linux Landlock ABI >= 3; no permissive fallback.
"""

FILE_WRITE_SCRIPT = r'''
import ctypes
import os
import platform
import sys


def restrict():
    if platform.machine() not in ("x86_64", "aarch64"):
        raise RuntimeError("Unsupported Landlock architecture")
    libc = ctypes.CDLL(None, use_errno=True)
    abi = libc.syscall(444, 0, 0, 1)  # landlock_create_ruleset(VERSION)
    if abi < 3:
        raise RuntimeError("Landlock ABI 3 required")

    class Ruleset(ctypes.Structure):
        _fields_ = [("handled_access_fs", ctypes.c_uint64)]

    class PathRule(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]

    # WRITE_FILE, REMOVE_DIR/FILE, MAKE_*, REFER and TRUNCATE. Reads stay native.
    writes = (1 << 1) | sum(1 << bit for bit in range(4, 15))
    ruleset = Ruleset(writes)
    fd = libc.syscall(444, ctypes.byref(ruleset), ctypes.sizeof(ruleset), 0)
    if fd < 0:
        raise RuntimeError("Cannot create Landlock ruleset")
    try:
        for path, access in (("/workspace", writes), ("/dev/null", 1 << 1)):
            parent = os.open(path, os.O_PATH | os.O_CLOEXEC | os.O_NOFOLLOW)
            try:
                rule = PathRule(access, parent)
                if libc.syscall(445, fd, 1, ctypes.byref(rule), 0) != 0:
                    raise RuntimeError("Cannot add Landlock rule")
            finally:
                os.close(parent)
        if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
            raise RuntimeError("Cannot disable privilege escalation")
        if libc.syscall(446, fd, 0) != 0:
            raise RuntimeError("Cannot enforce Landlock ruleset")
    finally:
        os.close(fd)


try:
    restrict()
except Exception:
    sys.exit("Native file writes blocked: sandbox.file_boundary_unavailable")
os.execv("/bin/bash", ["/bin/bash", "-c", sys.argv[1]])
'''
