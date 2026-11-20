# kubernetes_control_plane_host.py - Kubernetes control plane, host side (layer 2).
#
# Collector contract: docs/reference/COMPONENT_COLLECTOR_CONTRACT.md. Run by
# ansible/files/component_collector_guard.py, which provides `g` and `target`.
# Read-only. No cluster API call.
#
# Stores, for the verified control plane processes on this host: the flags each
# was started with; the mode and owner of the static pod manifests, the etcd
# data directory, the control plane kubeconfig files, the PKI tree and the CNI
# files; and from three files the API server names: the audit policy, the
# resource and provider names of the encryption configuration (never its
# keys), and the anonymous section of the authentication configuration. Key
# files and kubeconfig contents are never read. Field names follow the input
# contract of the CIS Kubernetes policy (benchmarks/cis/kubernetes).

FIELD = {"kube-apiserver": "api_server", "kube-controller-manager": "controller_manager",
         "kube-scheduler": "scheduler", "etcd": "etcd"}
KDIR = ["/etc/kubernetes"]
MANIFESTS = "/etc/kubernetes/manifests"

procs = {}
for name in FIELD:
    found = g.processes(name, accounts="root")
    if found:
        procs[name] = found[0]

files = {
    "manifests": g.stat([MANIFESTS + "/*"], KDIR),
    "control_plane_confs": g.stat(["/etc/kubernetes/" + n for n in
                                   ("admin.conf", "super-admin.conf", "scheduler.conf", "controller-manager.conf")], KDIR),
    "pki": g.stat(["/etc/kubernetes/pki"], KDIR, tree=True),
    "cni": [e for e in g.stat(["/etc/cni/net.d/*"], ["/etc/cni/net.d"], limit=500)],
}
facts = {}
for name, proc in procs.items():
    facts[FIELD[name]] = {"flags": proc.flags()}
if "etcd" in procs:
    data_dir = procs["etcd"].flags().get("data-dir") or "/var/lib/etcd"
    files["etcd_data"] = g.stat([data_dir.rstrip("/")], ["/var/lib"], procs["etcd"])

not_read = []
api = procs.get("kube-apiserver")
if api:
    flags = api.flags()
    for flag, field in (("audit-policy-file", "audit_policy"), ("encryption-provider-config", "encryption_config"),
                        ("authentication-config", "authentication_config")):
        if not flags.get(flag):
            continue
        text = g.read(flags[flag], KDIR, api)
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

# What is inside: the image of each static pod. Only the image line is kept.
children = []
reader = api or (list(procs.values())[0] if procs else None)
if reader:
    for entry in files["manifests"]:
        if not re.search(r"\.(yaml|yml)$", entry["path"]):
            continue
        text = g.read(entry["path"], [MANIFESTS], reader) or ""
        for image in re.findall(r"(?m)^\s*-?\s*image:\s*[\"']?([^\"'\s#]+)", text)[:20]:
            children.append({"kind": "container_image", "value": image[:300],
                             "name": re.sub(r"\.(yaml|yml)$", "", entry["path"].rsplit("/", 1)[-1])[:200],
                             "detail": {"source": "static pod manifest"}})

files = {name: entries for name, entries in files.items() if entries}
if not procs and not files:
    g.unverified("control plane")
else:
    facts["files"] = files
    facts["collection"] = {"processes_verified": sorted(procs), "files_not_read": not_read,
                           "processes_not_verified": [r["name"] + ": " + r["why"] for r in g.rejected][:20],
                           "manifest_dir": MANIFESTS}
    g.collected(facts, children=children)
