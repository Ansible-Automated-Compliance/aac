#!/usr/bin/env python3
"""
component_collector_guard.py - the only way a component collector touches a host.

Every collector (ansible/tasks/component_collectors/<key>_<layer>.py) is run
by this guard, on the managed host for the host side and on the controller for
the service side. A collector has no imports and no file or process access of
its own: it calls the guard, and the guard enforces the rules of the collector
contract (docs/reference/COMPONENT_COLLECTOR_CONTRACT.md):

  processes()   a process counts only when it is verified: its executable is a
                root-owned binary in a system path with the expected name, it
                runs as the expected account (resolved on the host), it is not
                in a container, and its parent is init. A process name alone
                proves nothing: any local user can choose one. Identity is
                never taken from the inspected process or from its container.
  stat()/read() every path is resolved first and must sit under a directory the
                collector names. It is then opened one component at a time,
                each from the descriptor of the one before and never through a
                symbolic link; type, owner and mode come from the opened
                descriptor. A service's file is read as the service's own
                account; a system file only when it is root-owned.
  scrub()       secret values are replaced before anything leaves the host.
  result        one line, base64. Nothing a host returned is ever placed in an
                Ansible variable as text, so it cannot be templated.

Python 3.6 or later, standard library only. Read-only: it opens nothing for
writing and runs no command.
"""
import base64
import fnmatch
import json
import os
import pwd
import grp
import re
import stat as statmod
import sys

REDACTED = "<redacted>"
PROC = "/proc"
# Where a trusted service binary may live. The catalog can add directories
# (`collector_guard.binary_dirs`, delivered in the collector input).
SYSTEM_DIRS = ("/usr/bin", "/usr/sbin", "/usr/local/bin", "/usr/local/sbin", "/usr/libexec", "/usr/lib",
               "/usr/lib64", "/bin", "/sbin", "/opt")
INIT_NAMES = ("systemd", "init")
MAX_READ = 262144
MAX_ARGS = 400

# ── Secret values ────────────────────────────────────────────────────────────
# Applied on the host to every string a collector returns, and again by
# scripts/layered_collection.py before anything is stored.
_VALUE = r"""("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|[^\s&;,'"]+)"""
_SECRET_NAME = (r"(?<![A-Za-z0-9])([A-Za-z0-9_.-]*?(?:password|passwd|passphrase|secrets?|tokens?|"
                r"api[_-]?key|access[_-]?key|private[_-]?key))")
SCRUB_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)", re.S), REDACTED),
    (re.compile(r"(?i)" + _SECRET_NAME + r"(\s*[=:]\s*)" + _VALUE), r"\1\2" + REDACTED),
    (re.compile(r"(://)[^/\s:@]+:[^@\s/]+@"), r"\1" + REDACTED + "@"),
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 " + REDACTED),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*"), REDACTED),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), REDACTED),
]
PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
SECRET_KEYS = {"password", "passwd", "passphrase", "token", "secret", "bearer_token", "bearertoken",
               "api_key", "apikey", "private_key", "privatekey", "client_key_data", "client-key-data",
               "client_secret", "access_key", "secret_key", "secret_access_key", "id_token", "refresh_token"}


def scrub_text(text):
    """A string with every secret-shaped value replaced."""
    for pattern, repl in SCRUB_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def scrub(value):
    """Any JSON value with secret-shaped values, and values of secret-named fields, replaced."""
    if isinstance(value, dict):
        return {k: (REDACTED if isinstance(v, str) and v and str(k).lower() in SECRET_KEYS else scrub(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        return scrub_text(value)
    return value


# ── A small YAML reader, for hosts without PyYAML ────────────────────────────

def _scalar(text):
    t = text.strip()
    if not t or t in ("~", "null"):
        return None
    if (t[0] == t[-1] == '"' or t[0] == t[-1] == "'") and len(t) >= 2:
        return t[1:-1]
    if t in ("true", "True"):
        return True
    if t in ("false", "False"):
        return False
    if t.startswith("[") and t.endswith("]"):
        inner = t[1:-1].strip()
        return [_scalar(x) for x in _split_flow(inner)] if inner else []
    if t == "{}":
        return {}
    if re.match(r"^-?[0-9]+$", t):
        return int(t)
    return t


def _split_flow(text):
    out, cur, quote = [], "", ""
    for ch in text:
        if quote:
            cur += ch
            quote = "" if ch == quote else quote
        elif ch in "\"'":
            quote, cur = ch, cur + ch
        elif ch == ",":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return out


def mini_yaml(text):
    """Block mappings and lists, flow lists and plain scalars. Enough for
    configuration files; no anchors, tags or multi-line scalars. Returns None
    when the text is outside that subset."""
    lines = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#") or raw.strip() in ("---", "..."):
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())] or re.search(r"(:|-)\s+[|>][-+]?\s*$", raw):
            return None
        body = re.sub(r"\s+#.*$", "", raw.rstrip())
        lines.append((len(body) - len(body.lstrip()), body.strip()))
    pos = [0]

    def block(indent):
        if pos[0] >= len(lines):
            return None
        if lines[pos[0]][1].startswith("- ") or lines[pos[0]][1] == "-":
            out = []
            while pos[0] < len(lines) and lines[pos[0]][0] == indent and \
                    (lines[pos[0]][1].startswith("- ") or lines[pos[0]][1] == "-"):
                rest = lines[pos[0]][1][1:].strip()
                if not rest:
                    pos[0] += 1
                    out.append(block(lines[pos[0]][0]) if pos[0] < len(lines) and lines[pos[0]][0] > indent else None)
                elif re.match(r"^[^\s\"'\[{][^:]*:(\s|$)", rest):
                    child = indent + 2
                    lines[pos[0]] = (child, rest)
                    out.append(block(child))
                else:
                    pos[0] += 1
                    out.append(_scalar(rest))
            return out
        out = {}
        while pos[0] < len(lines) and lines[pos[0]][0] == indent and not lines[pos[0]][1].startswith("- "):
            m = re.match(r"^(\"[^\"]*\"|'[^']*'|[^:]+):(?:\s+(.*))?$", lines[pos[0]][1])
            if not m:
                raise ValueError("not a mapping line")
            key, rest = _scalar(m.group(1)), m.group(2)
            pos[0] += 1
            if rest is None or rest == "":
                nxt = lines[pos[0]] if pos[0] < len(lines) else None
                if nxt and (nxt[0] > indent or (nxt[0] == indent and nxt[1].startswith("- "))):
                    out[str(key)] = block(nxt[0])
                else:
                    out[str(key)] = None
            else:
                out[str(key)] = _scalar(rest)
        return out

    try:
        doc = block(lines[0][0]) if lines else {}
        return doc if pos[0] >= len(lines) else None
    except (ValueError, IndexError):
        return None


def parse_yaml(text):
    try:
        import yaml  # PyYAML when the host has it
        return yaml.safe_load(text)
    except ImportError:
        return mini_yaml(text)
    except Exception:  # a document PyYAML rejects is not parsed by the fallback either
        return None


# ── Verified processes ───────────────────────────────────────────────────────

class Proc:
    """A process the guard has verified. Collectors receive nothing else."""

    def __init__(self, pid, name, uid, gid, exe, args, cwd):
        self.pid, self.name, self.uid, self.gid = pid, name, uid, gid
        self.exe, self.args, self.cwd = exe, args, cwd
        try:
            self.user = pwd.getpwuid(uid).pw_name
        except KeyError:
            self.user = str(uid)

    def flags(self):
        return flags_of(self.args)

    def arg_value(self, prefix):
        for a in self.args:
            if a.startswith(prefix):
                return a[len(prefix):]
        return ""


def flags_of(args):
    """`--name=value` arguments as {name: value}; `--name` alone is "true".
    A flag whose name marks a secret has its value replaced."""
    out = {}
    for a in args:
        if isinstance(a, str) and a.startswith("--") and len(a) > 2:
            name, _, value = a[2:].partition("=")
            value = value if "=" in a else "true"
            out[name] = REDACTED if scrub_text("%s=%s" % (name, value)) != "%s=%s" % (name, value) else value[:2000]
    return out


def _read_small(path, limit=65536):
    with open(path, "rb") as fh:
        return fh.read(limit)


def _status(pid):
    out = {}
    for line in _read_small(PROC + "/%d/status" % pid).decode("utf-8", "replace").splitlines():
        k, _, v = line.partition(":")
        out[k] = v.split()
    return out


def _root_owned_chain(path):
    """Why `path` is not a root-owned file that only root can replace ("" when it is)."""
    cur = path
    while True:
        try:
            st = os.lstat(cur)
        except OSError:
            return "%s cannot be read" % cur
        if st.st_uid != 0:
            return "%s is not owned by root" % cur
        if st.st_mode & 0o022 and not (statmod.S_ISDIR(st.st_mode) and st.st_mode & statmod.S_ISVTX):
            return "%s is writable by others" % cur
        if cur == "/":
            return ""
        cur = os.path.dirname(cur)


def _in_system_dir(path, extra=()):
    return any(fnmatch.fnmatch(path, d.rstrip("/") + "/*") for d in tuple(SYSTEM_DIRS) + tuple(extra))


def _host_binary_fault(pid, extra=()):
    """Why the executable of a process cannot be trusted ("" when it can)."""
    try:
        exe = os.readlink(PROC + "/%d/exe" % pid)
    except OSError:
        return "", "its executable cannot be read"
    if exe.endswith(" (deleted)"):
        return exe, "its executable was deleted or replaced"
    real = os.path.realpath(exe)
    if not _in_system_dir(real, extra):
        return real, "its executable %s is not in a system path" % real
    return real, _root_owned_chain(real)


def _same_mount_ns(pid):
    return os.readlink(PROC + "/%d/ns/mnt" % pid) == os.readlink(PROC + "/self/ns/mnt")


# ── Descriptor-based file access ─────────────────────────────────────────────
# A path is resolved and compared first, then the RESOLVED path is opened one
# component at a time, each relative to the descriptor of the one before and
# never through a symbolic link. Type, owner and mode are read from the opened
# descriptor, and the data is read from that same descriptor. A component that
# is swapped for a link between the check and the open makes the open fail.

_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _between_check_and_use(path):
    """Test hook: runs after a path was accepted and before it is opened."""


def _open_parent(real, root_owned_only=False):
    """An fd for the directory that holds `real`, reached without following a link."""
    parts = [p for p in real.split("/") if p]
    fd = os.open("/", _DIR_FLAGS)
    try:
        for part in parts[:-1]:
            nxt = os.open(part, _DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = nxt
            if root_owned_only:
                st = os.fstat(fd)
                if st.st_uid != 0 or (st.st_mode & 0o022 and not st.st_mode & statmod.S_ISVTX):
                    raise OSError("a directory on the way is not root-owned or is writable by others")
    except OSError:
        os.close(fd)
        raise
    return fd, (parts[-1] if parts else ".")


def _confined(path, under):
    """(resolved path, "") when `path` resolves under an allowed directory, else (None, why)."""
    if not isinstance(path, str) or not path.startswith("/") or "\0" in path:
        return None, "not an absolute path"
    real = os.path.realpath(path)
    allowed = [os.path.realpath(u) for u in under if isinstance(u, str) and u.startswith("/")]
    if not any(real == a or real.startswith(a.rstrip("/") + "/") for a in allowed if a != "/"):
        return None, "outside the expected directories"
    return real, ""


def _entry(logical, st):
    try:
        owner = pwd.getpwuid(st.st_uid).pw_name
    except KeyError:
        owner = str(st.st_uid)
    try:
        group = grp.getgrgid(st.st_gid).gr_name
    except KeyError:
        group = str(st.st_gid)
    return {"path": logical, "mode": "%o" % statmod.S_IMODE(st.st_mode), "owner": owner, "group": group}


class Guard:
    def __init__(self, target):
        self.target = target
        self.candidates = []    # every process that carried an expected name, and what was decided
        self.notes = []
        self._result = None
        self._root = os.geteuid() == 0
        cfg = target.get("guard") or {}
        self._dirs = tuple(str(d) for d in cfg.get("binary_dirs") or [] if str(d).startswith("/"))

    @property
    def rejected(self):
        return [c for c in self.candidates if not c["accepted"]]

    # -- processes ------------------------------------------------------------
    def _verify(self, pid, name, exe_names, accounts):
        st = _status(pid)
        uids, gids = set(st.get("Uid", [])), st.get("Gid", ["0"])
        if len(uids) != 1:
            return None, "it runs with mixed user ids"
        uid, gid = int(uids.pop()), int(gids[0])
        try:
            same_ns = _same_mount_ns(pid)
            exe_link = os.readlink(PROC + "/%d/exe" % pid)
        except OSError:
            return None, "its executable or namespace cannot be read (root is needed)"
        if not same_ns:
            # Identity is never taken from the inspected process or its container,
            # and nothing in this version can tie a container to an expected image.
            return None, "it runs in a container, and collection inside containers is not enabled"
        if exe_link.endswith(" (deleted)"):
            return None, "its executable was deleted or replaced"
        if not any(fnmatch.fnmatch(os.path.basename(exe_link), pat) for pat in exe_names):
            return None, "its executable is %s, not %s" % (os.path.basename(exe_link), " or ".join(exe_names))
        exe, fault = _host_binary_fault(pid, self._dirs)
        if fault:
            return None, fault
        # The expected accounts are resolved on the host, by name.
        wanted = {0} if accounts == "root" else set()
        for a in ([] if accounts == "root" else accounts):
            try:
                wanted.add(pwd.getpwnam(a).pw_uid)
            except KeyError:
                pass
        if accounts != "root":
            wanted.discard(0)
        if uid not in wanted:
            return None, "it runs as uid %d, not as %s" % (uid, "root" if accounts == "root" else "/".join(accounts))
        ppid = int(st["PPid"][0])
        if ppid > 0:
            try:
                pcomm = _read_small(PROC + "/%d/comm" % ppid).decode("utf-8", "replace").strip()
            except OSError:
                pcomm = None
            if pcomm in [n[:15] for n in (name,) + tuple(exe_names)]:
                return None, "child"            # a worker of the same service, not a main process
            if ppid != 1:
                return None, "its parent (%s) is not init" % (pcomm or "unreadable")
        try:
            raw = _read_small(PROC + "/%d/cmdline" % pid, 131072).split(b"\0")
            args = [a.decode("utf-8", "replace")[:2000] for a in raw if a][:MAX_ARGS]
            cwd = os.readlink(PROC + "/%d/cwd" % pid)
        except OSError:
            return None, "its command line or working directory cannot be read (root is needed)"
        return Proc(pid, name, uid, gid, exe, args, cwd), ""

    def processes(self, *names, exe_names=None, accounts="root"):
        """Every verified main process with one of these command names, in pid order.

        accounts: "root", or the names of the accounts the service may run as,
        resolved on this host. Every process that carries a name is recorded in
        `candidates` with the decision and the reason; one that fails a check is
        never returned. The collector decides what several verified processes mean.
        """
        exe_names = tuple(exe_names or names)
        found = []
        for entry in sorted((e for e in os.listdir(PROC) if e.isdigit()), key=int):
            pid = int(entry)
            try:
                comm = _read_small(PROC + "/%d/comm" % pid).decode("utf-8", "replace").strip()
            except OSError:
                continue
            name = next((n for n in names if comm == n[:15]), None)
            if name is None or pid == os.getpid():
                continue
            try:
                proc, why = self._verify(pid, name, exe_names, accounts)
            except (OSError, KeyError, ValueError, IndexError):
                proc, why = None, "it went away or cannot be read"
            if why == "child":
                continue
            self.candidates.append({"name": name, "pid": pid, "accepted": proc is not None,
                                    "why": "verified: %s, uid %d" % (proc.exe, proc.uid) if proc else why})
            if proc:
                found.append(proc)
        return found

    def seen(self, name):
        """True when any process carries this name, verified or not."""
        return any(c["name"] == name for c in self.candidates)

    # -- files ----------------------------------------------------------------
    def stat(self, paths, under, tree=False, limit=2000):
        """Mode and owner of each path that exists and resolves under `under`.
        A trailing `/*` lists a directory's entries; tree=True walks it. Nothing
        is opened through a symbolic link."""
        out, seen = [], set()

        def add_at(dir_fd, name, logical):
            if logical in seen or len(out) >= limit:
                return None
            try:
                st = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
            except OSError:
                return None
            seen.add(logical)
            out.append(_entry(logical, st))
            return st

        def walk(dir_fd, logical):
            try:
                names = sorted(os.listdir(dir_fd))
            except OSError:
                return
            for n in names:
                st = add_at(dir_fd, n, logical.rstrip("/") + "/" + n)
                if tree and st is not None and statmod.S_ISDIR(st.st_mode) and len(out) < limit:
                    try:
                        sub = os.open(n, _DIR_FLAGS, dir_fd=dir_fd)
                    except OSError:
                        continue
                    try:
                        walk(sub, logical.rstrip("/") + "/" + n)
                    finally:
                        os.close(sub)

        for path in paths:
            if not path:
                continue
            listing = path.endswith("/*")
            real, _ = _confined(path[:-2] if listing else path, under)
            if real is None:
                continue
            _between_check_and_use(real)
            try:
                parent, name = _open_parent(real)
            except OSError:
                continue
            try:
                if not listing:
                    add_at(parent, name, real)
                if listing or tree:
                    try:
                        fd = os.open(name, _DIR_FLAGS, dir_fd=parent)
                    except OSError:
                        continue
                    try:
                        walk(fd, real)
                    finally:
                        os.close(fd)
            finally:
                os.close(parent)
        if len(out) >= limit:
            self.notes.append("a file list was capped at %d entries" % limit)
        return out

    def read(self, path, under, proc=None, max_bytes=MAX_READ):
        """The text of one regular file, with secret-shaped values replaced.

        With a verified process: read as that process's own account (after
        dropping to it), and only a file owned by that account or by root.
        Without one: only a root-owned file that others cannot write, reached
        through root-owned directories (a system configuration file).
        None, with a note, when any rule is not met.
        """
        real, why = _confined(path, under)
        if real is None:
            self.notes.append("not read: %s (%s)" % (scrub_text(str(path))[:200], why))
            return None
        _between_check_and_use(real)
        owners = (0,) if proc is None else (0, proc.uid)
        r, w = os.pipe()
        child = os.fork()
        if child == 0:
            code = 3
            try:
                os.close(r)
                if proc is not None and self._root and proc.uid != 0:
                    os.setgroups([])
                    os.setgid(proc.gid)
                    os.setuid(proc.uid)
                parent, name = _open_parent(real, root_owned_only=proc is None)
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                st = os.fstat(fd)               # the opened file itself, not the path
                if not statmod.S_ISREG(st.st_mode) or st.st_uid not in owners \
                        or (proc is None and st.st_mode & 0o022):
                    code = 4
                else:
                    left = max_bytes
                    while left > 0:
                        buf = os.read(fd, min(65536, left))
                        if not buf:
                            break
                        os.write(w, buf)
                        left -= len(buf)
                    code = 5 if st.st_size > max_bytes else 0
            except BaseException:
                pass
            os._exit(code)
        os.close(w)
        chunks = []
        while True:
            buf = os.read(r, 65536)
            if not buf:
                break
            chunks.append(buf)
        os.close(r)
        code = os.waitpid(child, 0)[1] >> 8
        if code == 4:
            self.notes.append("not read: %s (not a regular file owned by the expected account)" % real[:200])
            return None
        if code not in (0, 5):
            self.notes.append("not read: %s (missing, not readable by the service account, or reached "
                              "through a link)" % real[:200])
            return None
        if code == 5:
            self.notes.append("%s was read up to %d bytes" % (real[:200], max_bytes))
        return scrub_text(b"".join(chunks).decode("utf-8", "replace"))

    # -- helpers a collector may use -----------------------------------------
    scrub = staticmethod(scrub)
    scrub_text = staticmethod(scrub_text)
    parse_yaml = staticmethod(parse_yaml)
    flags_of = staticmethod(flags_of)

    def env(self, name):
        """A credential value, service side only: only the names the catalog lists."""
        return os.environ.get(name, "") if name in (self.target.get("credential_env") or []) else ""

    # -- result ---------------------------------------------------------------
    def collected(self, facts, instance=None, children=None):
        self._result = {"status": "collected", "facts": facts}
        if instance:
            self._result["instance"] = instance
        if children:
            self._result["children"] = children

    def not_collected(self, reason):
        self._result = {"status": "not_collected", "reason": str(reason)[:300]}

    def unverified(self, what):
        """The standard outcome when no process could be verified."""
        if self.rejected:
            first = self.rejected[0]
            self.not_collected(("process could not be verified: a %s process is running but %s"
                                % (first["name"], first["why"]))[:300])
        else:
            self.not_collected("no running %s process found on this host" % what)

    def finish(self):
        result = self._result or {"status": "not_collected", "reason": "the collector set no result"}
        notes = list(self.notes)
        # Every process that carried an expected name, and what was decided about it.
        notes += ["process %s (pid %d): %s" % (c["name"], c["pid"],
                                               c["why"] if c["accepted"] else "refused: " + c["why"])
                  for c in self.candidates[:20]]
        notes = [scrub_text(n)[:300] for n in notes][:50]
        if notes:
            result["notes"] = notes
        return scrub(result)


_ALLOWED_BUILTINS = ("abs", "all", "any", "bool", "dict", "enumerate", "filter", "float", "int", "isinstance", "len",
                     "list", "map", "max", "min", "range", "repr", "reversed", "set", "sorted", "str", "sum",
                     "tuple", "zip", "True", "False", "None", "ValueError", "KeyError", "TypeError", "IndexError",
                     "Exception")


_FORBIDDEN_NAMES = {"open", "exec", "eval", "compile", "getattr", "setattr", "delattr", "globals", "locals", "vars",
                    "input", "breakpoint", "os", "sys", "subprocess", "pathlib", "shutil", "socket", "importlib"}


def check_code(code):
    """Faults that make a collector body unacceptable ([] means it may run).

    A collector reaches the host only through the guard: no import, no name
    that opens files or runs commands, no attribute that starts with an
    underscore (which is how the guard's own internals would be reached), and
    no Jinja delimiter anywhere in the file.
    """
    import ast
    faults = []
    for mark in ("{{", "{%", "{#"):
        if mark in code:
            faults.append("contains %r" % mark)
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return faults + ["does not parse: %s" % exc.msg]
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            faults.append("line %d: import is not allowed" % node.lineno)
        elif isinstance(node, ast.Name) and (node.id in _FORBIDDEN_NAMES or node.id.startswith("__")):
            faults.append("line %d: %s is not allowed" % (node.lineno, node.id))
        elif isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            faults.append("line %d: attribute %s is not allowed" % (node.lineno, node.attr))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and "/proc" in node.value:
            faults.append("line %d: a collector does not read /proc; use g.processes()" % node.lineno)
    return faults


def run(code, target):
    """Run one collector body under the guard and return its result."""
    import builtins
    guard = Guard(target)
    faults = check_code(code)
    if faults:
        guard.not_collected(("collector refused: " + "; ".join(faults))[:300])
        return guard.finish()
    env = {"__builtins__": {n: getattr(builtins, n) for n in _ALLOWED_BUILTINS},
           "g": guard, "target": target, "re": re}
    try:
        exec(compile(code, target.get("collector", {}).get("file", "collector"), "exec"), env)  # noqa: S102
    except Exception as exc:  # a collector fault is an outcome, never a crash
        guard.not_collected(("collector failed: %s" % type(exc).__name__)[:300])
    return guard.finish()


def main():
    target = json.loads(base64.b64decode(os.environ["LC_TARGET_B64"]).decode("utf-8"))
    code = base64.b64decode(os.environ["LC_CODE_B64"]).decode("utf-8")
    result = run(code, target)
    blob = json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sys.stdout.write("LCRESULT:" + base64.b64encode(blob).decode("ascii") + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
