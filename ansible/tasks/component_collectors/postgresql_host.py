# postgresql_host.py - PostgreSQL server, host side (layer 2).
#
# Collector contract: docs/reference/COMPONENT_COLLECTOR_CONTRACT.md. Run by
# ansible/files/component_collector_guard.py, which provides `g` and `target`.
# Read-only. Opens no database session.
#
# Stores an allowlist of settings, the rules of pg_hba.conf, and the mode and
# owner of the data directory and the configuration files. A setting that is
# not on the list is named in `settings_not_stored` without its value:
# connection strings and shell commands (primary_conninfo, archive_command,
# restore_command, ...) can hold passwords. Files named by `include`
# directives are not followed; the result says so. Every verified postmaster on
# the host is recorded under `servers`. A server in a container is not
# collected in this version: the guard refuses a process in a container.

KEEP = set("""
listen_addresses port max_connections superuser_reserved_connections unix_socket_directories unix_socket_group
unix_socket_permissions authentication_timeout password_encryption krb_server_keyfile db_user_namespace
ssl ssl_ca_file ssl_cert_file ssl_crl_file ssl_key_file ssl_ciphers ssl_prefer_server_ciphers
ssl_min_protocol_version ssl_max_protocol_version ssl_ecdh_curve
shared_preload_libraries session_preload_libraries local_preload_libraries
fsync full_page_writes synchronous_commit wal_level archive_mode hot_standby max_wal_senders data_checksums
log_destination logging_collector log_directory log_filename log_file_mode log_truncate_on_rotation
log_rotation_age log_rotation_size syslog_facility syslog_ident log_min_messages log_min_error_statement
log_min_duration_statement log_checkpoints log_connections log_disconnections log_duration log_error_verbosity
log_hostname log_line_prefix log_lock_waits log_statement log_replication_commands log_timezone timezone
debug_print_parse debug_print_rewritten debug_print_plan debug_pretty_print
row_security statement_timeout idle_session_timeout idle_in_transaction_session_timeout tcp_keepalives_idle
hba_file ident_file external_pid_file
pgaudit.log pgaudit.log_catalog pgaudit.log_client pgaudit.log_level pgaudit.log_parameter pgaudit.log_relation
pgaudit.log_statement_once pgaudit.role
""".split())
ACCOUNTS = ["postgres", "enterprisedb"]
CONFIG_DIRS = ["/etc/postgresql", "/etc/postgres", "/var/lib/pgsql", "/var/lib/postgresql"]


def settings_of(text, settings, not_stored, notes):
    for raw in text.splitlines():
        line = raw.strip()
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_.]*)\s*=?\s*(.*)$", line)
        if not line or line.startswith("#") or not m:
            continue
        name, rest = m.group(1).lower(), m.group(2)
        if name in ("include", "include_if_exists", "include_dir"):
            notes.append("an %s directive is present; included files were not read" % name)
            continue
        q = re.match(r"^'((?:[^']|'')*)'", rest)
        value = q.group(1).replace("''", "'") if q else re.split(r"\s|#", rest, maxsplit=1)[0]
        if name in KEEP:
            settings[name] = value[:500]
        else:
            not_stored.add(name)


def hba_rules(text):
    rules = []
    for raw in text.splitlines():
        line = re.sub(r"\s+#.*$", "", raw.strip())
        if not line or line.startswith("#"):
            continue
        f = line.split()
        kind = f[0].lower()
        if kind == "local" and len(f) >= 4:
            rules.append({"type": kind, "database": f[1], "user": f[2], "address": "", "method": f[3],
                          "options": f[4:]})
        elif kind.startswith("host") and len(f) >= 5:
            mask = len(f) >= 6 and re.match(r"^[0-9]+\.[0-9.]+$|^[0-9a-fA-F:]+$", f[4]) is not None
            rules.append({"type": kind, "database": f[1], "user": f[2],
                          "address": (f[3] + " " + f[4]) if mask else f[3],
                          "method": f[5] if mask else f[4], "options": f[6:] if mask else f[5:]})
        else:
            rules.append({"type": "unparsed", "fields": len(f)})
    return rules[:2000]


mains = g.processes("postgres", "postmaster", accounts=ACCOUNTS)
servers = []
for pm in mains[:8]:
    data = pm.cwd
    under = [data] + CONFIG_DIRS
    version = g.read(data + "/PG_VERSION", [data], pm, 64)
    if version is None:
        g.notes.append("postmaster pid %d: its data directory could not be read" % pm.pid)
        continue
    conf = pm.arg_value("config_file=") or pm.arg_value("--config_file=") or pm.arg_value("--config-file=") \
        or (data + "/postgresql.conf")
    settings, not_stored, sources = {}, set(), []
    for path in (conf, data + "/postgresql.auto.conf"):
        text = g.read(path, under, pm)
        if text is not None:
            sources.append(path)
            settings_of(text, settings, not_stored, g.notes)
    hba = settings.get("hba_file") or (data + "/pg_hba.conf")
    hba_text = g.read(hba, under, pm)
    servers.append({"version": version.strip()[:16], "data_directory": data, "hba_file": hba,
                    "postmaster_user": pm.user, "settings": settings, "settings_sources": sources,
                    "settings_not_stored": sorted(not_stored)[:300],
                    "hba_rules": hba_rules(hba_text) if hba_text is not None else [],
                    "hba_read": hba_text is not None,
                    "files": g.stat([data, conf, data + "/postgresql.auto.conf", hba], under)})
if not mains:
    g.unverified("postmaster")
elif not servers:
    g.not_collected("a verified postmaster is running but its data directory could not be read")
else:
    if len(mains) > 8:
        g.notes.append("%d verified postmaster processes; the first 8 were collected" % len(mains))
    first = servers[0]
    g.collected({"servers": servers},
                instance={"identity": re.sub(r"[^A-Za-z0-9._:/@-]", "_", "host/%s/port/%s"
                                             % (target["host"], first["settings"].get("port", "5432")))[:200],
                          "name": "PostgreSQL " + first["version"]})
