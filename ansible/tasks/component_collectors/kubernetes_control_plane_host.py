# kubernetes_control_plane_host.py - Kubernetes control plane, host side (layer 2).
#
# Collector contract: docs/reference/COMPONENT_COLLECTOR_CONTRACT.md. Run by
# ansible/files/component_collector_guard.py, which provides `g` and `target`.
# Read-only. No cluster API call.
#
# Stores, for the API server, controller manager, scheduler and etcd: the flags
# each is started with; the mode and owner of the static pod manifests, the
# etcd data directory, the control plane kubeconfig files, the PKI tree and
# the CNI files; and from three files the API server names: the audit policy,
# the resource and provider names of the encryption configuration (never its
# keys), and the anonymous section of the authentication configuration.
#
# Where the flags come from: a verified root process on the host when there is
# exactly one; otherwise the `command` of the component's static pod manifest
# in /etc/kubernetes/manifests, a root-owned file the kubelet starts the
# component from. A component that runs in a container (the usual case) is
# never read through its process. `collection.flags_source` says which.
# Key files and kubeconfig contents are never read. Field names follow the
# input contract of the CIS Kubernetes policy (benchmarks/cis/kubernetes).

FIELD = {"kube-apiserver": "api_server", "kube-controller-manager": "controller_manager",
         "kube-scheduler": "scheduler", "etcd": "etcd"}
KDIR = ["/etc/kubernetes"]
MANIFESTS = "/etc/kubernetes/manifests"

files = {
    "manifests": g.stat([MANIFESTS + "/*"], KDIR),
    "control_plane_confs": g.stat(["/etc/kubernetes/" + n for n in
                                   ("admin.conf", "super-admin.conf", "scheduler.conf", "controller-manager.conf")], KDIR),
    "pki": g.stat(["/etc/kubernetes/pki"], KDIR, tree=True),
    "cni": g.stat(["/etc/cni/net.d/*"], ["/etc/cni/net.d"], limit=500),
}

# Static pod manifests: root-owned system files, read without any process.
manifest_flags, children = {}, []
for entry in files["manifests"]:
    m = re.search(r"/([^/]+)\.(yaml|yml)$", entry["path"])
    if not m:
        continue
    text = g.read(entry["path"], [MANIFESTS])
    doc = g.parse_yaml(text) if text is not None else None
    containers = ((doc or {}).get("spec") or {}).get("containers") if isinstance(doc, dict) else None
    for c in containers if isinstance(containers, list) else []:
        if not isinstance(c, dict):
            continue
        if isinstance(c.get("image"), str):
            children.append({"kind": "container_image", "value": c["image"][:300], "name": m.group(1)[:200],
                             "detail": {"source": "static pod manifest"}})
        words = [w for w in (c.get("command") or []) + (c.get("args") or []) if isinstance(w, str)]
        if m.group(1) in FIELD and words and m.group(1) not in manifest_flags:
            manifest_flags[m.group(1)] = g.flags_of(words)

facts, source = {}, {}
for name, field in FIELD.items():
    found = g.processes(name, accounts="root")
    if len(found) == 1:
        facts[field] = {"flags": found[0].flags()}
        source[name] = "process"
    elif name in manifest_flags:
        facts[field] = {"flags": manifest_flags[name]}
        source[name] = "static pod manifest"
    elif len(found) > 1:
        g.notes.append("%d verified %s processes and no manifest: flags not stored" % (len(found), name))

if "etcd" in facts:
    data_dir = facts["etcd"]["flags"].get("data-dir") or "/var/lib/etcd"
    files["etcd_data"] = g.stat([data_dir.rstrip("/")], ["/var/lib"])

not_read = []
if "api_server" in facts:
    flags = facts["api_server"]["flags"]
    for flag, field in (("audit-policy-file", "audit_policy"), ("encryption-provider-config", "encryption_config"),
                        ("authentication-config", "authentication_config")):
        if not flags.get(flag):
            continue
        text = g.read(flags[flag], KDIR)
        doc = g.parse_yaml(text) if text is not None else None
        if not isinstance(doc, dict):
            not_read.append(flag + (": not read" if text is None else ": not parsed"))
        elif field == "audit_policy":
            facts["api_server"][field] = {"apiVersion": doc.get("apiVersion", ""), "kind": doc.get("kind", ""),
                                          "rules": doc.get("rules") or [], "omitStages": doc.get("omitStages") or []}
        elif field == "encryption_config":
            entries = []
            for e in doc.get("resources") or []:
                if isinstance(e, dict):
                    names = []
                    for prov in e.get("providers") or []:
                        if isinstance(prov, dict):
                            names.extend(sorted(prov))
                    entries.append({"resources": e.get("resources") or [], "providers": names})
            facts["api_server"][field] = {"resources": entries}
        else:
            anon = doc.get("anonymous")
            facts["api_server"][field] = {"anonymous": anon} if isinstance(anon, dict) else {}

files = {name: entries for name, entries in files.items() if entries}
if not facts and not files:
    g.unverified("control plane")
else:
    facts["files"] = files
    facts["collection"] = {"flags_source": source, "files_not_read": not_read, "manifest_dir": MANIFESTS}
    g.collected(facts, children=children)
