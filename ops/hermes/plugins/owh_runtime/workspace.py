"""Bounded file transfer executed by the immutable interpreter inside the sandbox."""

WORKSPACE_SCRIPT = r"""
import base64, hashlib, json, os, stat, sys
MAX_FILE = 64 * 1024 * 1024
request = json.load(sys.stdin)
root = os.open('/workspace', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
def parent(path):
    parts = path.split('/')
    if not parts or len(path) > 1024 or any(not p or p in ('.', '..', '.owh-runtime') or any(ord(c) < 32 for c in p) for p in parts):
        raise ValueError('Invalid path')
    fd = os.dup(root)
    for part in parts[:-1]:
        if request['op'] == 'write':
            try: os.mkdir(part, mode=0o700, dir_fd=fd)
            except FileExistsError: pass
        next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        os.close(fd)
        fd = next_fd
    return fd, parts[-1]
def read(fd, name):
    handle = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=fd)
    with os.fdopen(handle, 'rb') as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError('Regular files required')
        data = source.read(MAX_FILE + 1)
        if len(data) > MAX_FILE: raise ValueError('File too large')
        return data
if request['op'] == 'list':
    result, total = [], 0
    for directory, dirs, files, fd in os.fwalk('.', dir_fd=root, follow_symlinks=False):
        dirs[:] = [d for d in dirs if d != '.owh-runtime' and not stat.S_ISLNK(os.stat(d, dir_fd=fd, follow_symlinks=False).st_mode)]
        for name in files:
            if not stat.S_ISREG(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode): continue
            data = read(fd, name)
            total += len(data)
            if total > 256 * 1024 * 1024 or len(result) >= 10000: raise ValueError('Workspace too large')
            path = (directory[2:] + '/' if directory != '.' else '') + name
            result.append({'path': path, 'sha256': hashlib.sha256(data).hexdigest()})
    print(json.dumps(result))
else:
    fd, name = parent(request['path'])
    if request['op'] == 'read':
        print(json.dumps({'data': base64.b64encode(read(fd, name)).decode()}))
    elif request['op'] == 'write':
        data = base64.b64decode(request['data'], validate=True)
        if len(data) > MAX_FILE or hashlib.sha256(data).hexdigest() != request['sha256']: raise ValueError('Integrity error')
        handle = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=fd)
        with os.fdopen(handle, 'wb') as target:
            if not stat.S_ISREG(os.fstat(target.fileno()).st_mode): raise ValueError('Regular file required')
            target.write(data)
        print('{}')
    else: raise ValueError('Unknown operation')
    os.close(fd)
os.close(root)
"""
