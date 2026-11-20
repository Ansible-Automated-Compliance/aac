# kubelet_host.py - Kubernetes node (kubelet and kube-proxy), host side (layer 2).
#
# Collector contract: docs/reference/COMPONENT_COLLECTOR_CONTRACT.md. Run by
# ansible/files/component_collector_guard.py, which provides `g` and `target`.
# Read-only. No cluster API call.
#
# Stores the kubelet flags, an allowlist of KubeletConfiguration fields (the
# ones the CIS Kubernetes policy reads), the mode and owner of the kubelet unit
# file, kubeconfig, client CA file, configuration file and configuration
# directory, and for kube-proxy whether it runs, its flags, its metrics bind
# address and the mode and owner of its kubeconfig. Kubeconfig contents,
# certificates and keys are never read. Both processes must be verified root
# processes on the host; a path taken from a flag is used only inside the
# directories below. kube-proxy usually runs in a container, where the guard
# refuses it: then nothing about kube-proxy is stated, and the policy reports
# its checks as evidence missing.

KUBELET_DIRS = ["/var/lib/kubelet", "/etc/kubernetes"]
PROXY_DIRS = ["/var/lib/kube-proxy", "/etc/kubernetes", "/var/lib/kubelet"]
UNIT_DIRS = ["/usr/lib/systemd/system", "/etc/systemd/system", "/lib/systemd/system"]
KEEP = [["authentication", "anonymous", "enabled"], ["authentication", "webhook", "enabled"],
        ["authentication", "x509", "clientCAFile"], ["authorization", "mode"],
        ["featureGates", "RotateKubeletServerCertificate"], ["makeIPTablesUtilChains"], ["podPidsLimit"],
        ["rotateCertificates"], ["seccompDefault"], ["serverTLSBootstrap"], ["streamingConnectionIdleTimeout"],
        ["tlsCertFile"], ["tlsCipherSuites"], ["tlsPrivateKeyFile"], ["tlsMinVersion"], ["readOnlyPort"],
        ["protectKernelDefaults"], ["eventRecordQPS"], ["staticPodPath"], ["kind"], ["apiVersion"]]


def keep(doc):
    out = {}
    for path in KEEP:
        cur, ok = doc, True
        for part in path:
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and not isinstance(cur, dict):
            dst = out
            for part in path[:-1]:
                dst = dst.setdefault(part, {})
            dst[path[-1]] = cur
    return out


kubelets = g.processes("kubelet", accounts="root")
if not kubelets:
    g.unverified("kubelet")
elif len(kubelets) > 1:
    g.not_collected("%d verified kubelet processes on this host: which one configures the node is not clear"
                    % len(kubelets))
else:
    k = kubelets[0]
    flags = k.flags()
    kubelet = {"flags": flags}
    state = "no --config flag"
    config = {}
    if flags.get("config"):
        text = g.read(flags["config"], KUBELET_DIRS, k)
        doc = g.parse_yaml(text) if text is not None else None
        state = "ok" if isinstance(doc, dict) else ("not read" if text is None else "not parsed")
        if isinstance(doc, dict):
            config = keep(doc)
            kubelet["config"] = config
    client_ca = flags.get("client-ca-file") or config.get("authentication", {}).get("x509", {}).get("clientCAFile", "")
    files = {
        "kubelet_service": g.stat([d + "/kubelet.service" for d in UNIT_DIRS]
                                  + [d + "/kubelet.service.d/*" for d in UNIT_DIRS], UNIT_DIRS),
        "kubelet_kubeconfig": g.stat([flags.get("kubeconfig") or "/etc/kubernetes/kubelet.conf"], KUBELET_DIRS),
        "kubelet_client_ca": g.stat([client_ca], KUBELET_DIRS),
        "kubelet_config_yaml": g.stat([flags.get("config", "")], KUBELET_DIRS),
    }
    if flags.get("config-dir"):
        files["kubelet_config_dir"] = g.stat([flags["config-dir"], flags["config-dir"].rstrip("/") + "/*"],
                                             KUBELET_DIRS, limit=200)
    facts = {"kubelet": kubelet}
    proxies = g.processes("kube-proxy", accounts="root")
    if len(proxies) == 1:
        p = proxies[0]
        pflags = p.flags()
        proxy = {"running": True, "flags": pflags}
        files["kube_proxy_kubeconfig"] = g.stat(
            [pflags.get("kubeconfig", ""), "/var/lib/kube-proxy/kubeconfig.conf"], PROXY_DIRS)[:1]
        if pflags.get("config"):
            text = g.read(pflags["config"], PROXY_DIRS, p)
            if text is not None:
                m = re.search(r"(?m)^metricsBindAddress:\s*[\"']?([^\"'\s#]*)", text)
                proxy["config"] = {"metricsBindAddress": m.group(1)} if m else {}
        facts["kube_proxy"] = proxy
    elif not g.seen("kube-proxy"):
        facts["kube_proxy"] = {"running": False}
    facts["files"] = {name: entries for name, entries in files.items() if entries}
    facts["collection"] = {"kubelet_config_file": state,
                           "kube_proxy": "verified" if len(proxies) == 1 else
                                         ("not running" if not g.seen("kube-proxy") else "seen, not verified")}
    g.collected(facts)
