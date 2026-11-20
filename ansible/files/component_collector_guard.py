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
                runs as the expected account, and its parent is init or a
                verified container runtime. A process name alone proves nothing:
                any local user can choose one.
  stat()/read() every path is resolved first and must sit under a directory the
                collector names; files are read as the verified process's own
                account, never as root; a file must be owned by that account or
                by root.
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
# Where a trusted service binary may live. The catalog can add directories and
# names the container runtimes whose children count as started by a runtime
# (`collector_guard` in the catalog, delivered in the collector input).
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

    def __init__(self, pid, name, uid, gid, exe, args, cwd, in_container):
        self.pid, self.name, self.uid, self.gid = pid, name, uid, gid
        self.exe, self.args, self.cwd, self.in_container = exe, args, cwd, in_container
        try:
            self.user = pwd.getpwuid(uid).pw_name
        except KeyError:
            self.user = str(uid)

    def flags(self):
        """`--name=value` arguments as {name: value}; `--name` alone is "true"."""
        out = {}
        for a in self.args:
            if a.startswith("--") and len(a) > 2:
                name, _, value = a[2:].partition("=")
                value = value if "=" in a else "true"
                out[name] = REDACTED if scrub_text("%s=%s" % (name, value)) != "%s=%s" % (name, value) else value
        return out

    def arg_value(self, prefix):
        for a in self.args:
            if a.startswith(prefix):
                return a[len(prefix):]
        return ""


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
    """Why the executable of a process in our own mount namespace cannot be trusted."""
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


class Guard:
    def __init__(self, target):
        self.target = target
        self.rejected = []      # processes that carried an expected name and failed verification
        self.notes = []
        self._result = None
        self._root = os.geteuid() == 0
        cfg = target.get("guard") or {}
        self._runtimes = tuple(str(n)[:15] for n in cfg.get("runtime_parents") or [])   # comm keeps 15 characters
        self._dirs = tuple(str(d) for d in cfg.get("binary_dirs") or [] if str(d).startswith("/"))

    # -- processes ------------------------------------------------------------
    def _parent_fault(self, pid, ppid, names):
        if ppid == 0:
            return ""
        try:
            pcomm = _read_small(PROC + "/%d/comm" % ppid).decode().strip()
            if pcomm in [n[:15] for n in names]:
                return "child"      # a worker of the same service; never the main process
            if ppid == 1:
                return ""
            if not _same_mount_ns(ppid):
                return "its parent is in another namespace"
        except OSError:
            return "" if ppid == 1 else "its parent cannot be read"
        if pcomm in self._runtimes or pcomm in INIT_NAMES:
            _, fault = _host_binary_fault(ppid, self._dirs)
            if not fault and os.stat(PROC + "/%d" % ppid).st_uid in (0, os.stat(PROC + "/%d" % pid).st_uid):
                return ""
            return "its parent %s could not be verified" % pcomm
        return "its parent (%s) is neither init nor a container runtime" % pcomm

    def _runtime_ancestor(self, pid):
        """True when a root-owned, verified container runtime started this process."""
        cur = pid
        for _ in range(12):
            try:
                ppid = int(_status(cur)["PPid"][0])
                if ppid <= 1:
                    return False
                comm = _read_small(PROC + "/%d/comm" % ppid).decode().strip()
                if comm in self._runtimes and _same_mount_ns(ppid):
                    _, fault = _host_binary_fault(ppid, self._dirs)
                    return not fault and os.stat(PROC + "/%d" % ppid).st_uid == 0
                cur = ppid
            except (OSError, KeyError, ValueError):
                return False
        return False

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
        if exe_link.endswith(" (deleted)"):
            return None, "its executable was deleted or replaced"
        if not any(fnmatch.fnmatch(os.path.basename(exe_link), pat) for pat in exe_names):
            return None, "its executable is %s, not %s" % (os.path.basename(exe_link), " or ".join(exe_names))
        root = "" if same_ns else PROC + "/%d/root" % pid
        if same_ns:
            exe, fault = _host_binary_fault(pid, self._dirs)
            if fault:
                return None, fault
            wanted = {0} if accounts == "root" else set()
            for a in ([] if accounts == "root" else accounts):
                try:
                    wanted.add(pwd.getpwnam(a).pw_uid)
                except KeyError:
                    pass
            fault = self._parent_fault(pid, int(st["PPid"][0]), (name,) + tuple(exe_names))
            if fault:
                return None, fault
        else:
            exe = exe_link
            if not self._runtime_ancestor(pid):
                return None, "it is in a container that no verified, root-owned container runtime started"
            wanted = {0} if accounts == "root" else self._container_uids(root, accounts)
        if uid not in wanted:
            return None, "it runs as uid %d, not as %s" % (uid, "root" if accounts == "root" else "/".join(accounts))
        try:
            raw = _read_small(PROC + "/%d/cmdline" % pid, 131072).split(b"\0")
            args = [a.decode("utf-8", "replace")[:2000] for a in raw if a][:MAX_ARGS]
            cwd = os.readlink(PROC + "/%d/cwd" % pid)
        except OSError:
            return None, "its command line or working directory cannot be read (root is needed)"
        return Proc(pid, name, uid, gid, exe, args, cwd, not same_ns), ""

    def _container_uids(self, root, accounts):
        """The uids of the named accounts in a container's own passwd file."""
        path = root + "/etc/passwd"
        out = set()
        try:
            if statmod.S_ISLNK(os.lstat(path).st_mode) or statmod.S_ISLNK(os.lstat(root + "/etc").st_mode):
                return out
            for line in _read_small(path, 262144).decode("utf-8", "replace").splitlines():
                f = line.split(":")
                if len(f) > 2 and f[0] in accounts and f[2].isdigit():
                    out.add(int(f[2]))
        except OSError:
            pass
        return out

    def processes(self, *names, exe_names=None, accounts="root"):
        """Verified processes with one of these command names, lowest pid first.

        accounts: "root", or the account names the service is allowed to run as.
        A process that carries the name and fails a check is listed in
        `rejected` with the reason and is never returned.
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
            if proc:
                found.append(proc)
            elif why != "child":
                self.rejected.append({"name": name, "pid": pid, "why": why})
        return found

    # -- paths ----------------------------------------------------------------
    def _confine(self, path, under, proc):
        """(path to open, logical path) when `path` resolves under an allowed directory, else (None, why)."""
        if not isinstance(path, str) or not path.startswith("/") or "\0" in path:
            return None, "not an absolute path"
        root = PROC + "/%d/root" % proc.pid if (proc is not None and proc.in_container) else ""
        if root:
            logical = os.path.normpath(path)
            cur = ""
            for part in [p for p in logical.split("/") if p]:
                cur += "/" + part
                try:
                    if statmod.S_ISLNK(os.lstat(root + cur).st_mode):
                        return None, "a symbolic link in a container path is not followed"
                except OSError:
                    return None, "does not exist"
            allowed = [os.path.normpath(u) for u in under]
        else:
            logical = os.path.realpath(path)
            allowed = [os.path.realpath(u) for u in under]
        if not any(logical == a or logical.startswith(a.rstrip("/") + "/") for a in allowed if a and a != "/"):
            return None, "outside the expected directories"
        return root + logical, logical

    @staticmethod
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

    def stat(self, paths, under, proc=None, tree=False, limit=2000):
        """Mode and owner of each path that exists and resolves under `under`.
        A trailing `/*` lists a directory's entries; tree=True walks it."""
        out, seen = [], set()

        def add(candidate):
            real, logical = self._confine(candidate, under, proc)
            if real is None or logical in seen or len(out) >= limit:
                return
            try:
                st = os.lstat(real) if (proc is not None and proc.in_container) else os.stat(real)
            except OSError:
                return
            seen.add(logical)
            out.append(self._entry(logical, st))

        for path in paths:
            if not path:
                continue
            if path.endswith("/*") or tree:
                base = path[:-2] if path.endswith("/*") else path
                real, logical = self._confine(base, under, proc)
                if real is None or not os.path.isdir(real):
                    continue
                if tree:
                    add(base)
                    for dirpath, dirnames, filenames in os.walk(real):
                        for n in sorted(dirnames) + sorted(filenames):
                            add(os.path.join(logical + dirpath[len(real):], n))
                else:
                    for n in sorted(os.listdir(real)):
                        add(os.path.join(logical, n))
            else:
                add(path)
        if len(out) >= limit:
            self.notes.append("a file list was capped at %d entries" % limit)
        return out

    def read(self, path, under, proc, max_bytes=MAX_READ):
        """The text of one regular file, read as the verified process's account
        (never as root unless the process is root). None, with a note, when the
        path is outside `under`, is not owned by that account or root, or
        cannot be read. Secret-shaped values are already replaced."""
        if proc is None:
            raise ValueError("read() needs the verified process the file belongs to")
        real, logical = self._confine(path, under, proc)
        if real is None:
            self.notes.append("not read: %s (%s)" % (scrub_text(str(path))[:200], logical))
            return None
        try:
            st = os.lstat(real) if proc.in_container else os.stat(real)
        except OSError:
            self.notes.append("not read: %s (does not exist)" % logical[:200])
            return None
        if not statmod.S_ISREG(st.st_mode) or st.st_uid not in (0, proc.uid):
            self.notes.append("not read: %s (not a regular file owned by the service account or root)" % logical[:200])
            return None
        r, w = os.pipe()
        child = os.fork()
        if child == 0:
            try:
                os.close(r)
                if self._root and proc.uid != 0:
                    os.setgroups([])
                    os.setgid(proc.gid)
                    os.setuid(proc.uid)
                fd = os.open(real, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                data = os.read(fd, max_bytes)
                os.write(w, data)
                os._exit(0)
            except BaseException:
                os._exit(3)
        os.close(w)
        chunks = []
        while True:
            buf = os.read(r, 65536)
            if not buf:
                break
            chunks.append(buf)
        os.close(r)
        _, code = os.waitpid(child, 0)
        if code != 0:
            self.notes.append("not read: %s (not readable by the service account)" % logical[:200])
            return None
        if st.st_size > max_bytes:
            self.notes.append("%s was read up to %d bytes" % (logical[:200], max_bytes))
        return scrub_text(b"".join(chunks).decode("utf-8", "replace"))

    # -- helpers a collector may use -----------------------------------------
    scrub = staticmethod(scrub)
    scrub_text = staticmethod(scrub_text)
    parse_yaml = staticmethod(parse_yaml)

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
        """The standard outcome when a process carried the name and failed verification."""
        if self.rejected:
            first = self.rejected[0]
            self.not_collected(("process could not be verified: a %s process is running but %s"
                                % (first["name"], first["why"]))[:300])
        else:
            self.not_collected("no running %s process found on this host" % what)

    def finish(self):
        result = self._result or {"status": "not_collected", "reason": "the collector set no result"}
        notes = [scrub_text(n)[:300] for n in self.notes][:50]
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
