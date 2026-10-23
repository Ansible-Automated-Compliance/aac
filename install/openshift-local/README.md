# AAP 2.7 and Automation Orchestrator on OpenShift Local (CRC) — RHEL 9 Evaluation Install

**Version:** v2.0
**Date:** 2026-10-22
**Authors:** Tim Coulter · Claude (Anthropic)
**Audience:** a customer or partner team standing up Ansible Automation Platform 2.7 and Automation Orchestrator on one RHEL 9 machine for an evaluation or a proof of concept
**Applies to:** AAP 2.7 (operator channel `stable-2.7`), Automation Orchestrator (operator channel `stable`), OpenShift Local 2.6x, RHEL 9
**Tier:** evaluation (demo/field) — see `install/SUPPORT_MATRIX.md`. OpenShift Local is not a production platform, and neither is this install.

---

## 1. Scope

This guide installs three things on one RHEL 9 host and stops:

1. **OpenShift Local (CRC)**, a single-node OpenShift cluster in a VM under libvirt.
2. **Ansible Automation Platform 2.7** inside that cluster, with the Red Hat operator: gateway, controller, Event-Driven Ansible and Private Automation Hub.
3. **Automation Orchestrator** inside the same cluster, with its operator and a PostgreSQL for it, connected to the platform.

It does **not** install Ansible Automated Compliance. The AAC stack, its execution environment, the AAP project and templates, EDA activations and policy as code are the subject of the [AAC extended install guide](../existing-aap/extended/README.adoc), which is written for exactly the platform this guide leaves you with. Section 10 says what that guide needs from here.

Everything applied to the cluster is a shipped manifest under `install/openshift-local/manifests/`. The only edit required before applying is one database password.

### What you get

| Component | Where it runs | Reached at |
|---|---|---|
| OpenShift Local cluster | one VM on the host | `https://console-openshift-console.apps-crc.testing` |
| AAP 2.7: gateway, controller, EDA, Private Automation Hub | namespace `aap-operator` | `https://aap-aap-operator.apps-crc.testing` |
| Automation Orchestrator: UI, backend, workers, Temporal, Redis | namespace `automation-orchestrator` | `https://ao-automation-orchestrator.apps-crc.testing` |
| PostgreSQL 15 for Automation Orchestrator | namespace `automation-orchestrator` | in-cluster only |

## 2. Prerequisites

### Sizing

The platform operator can upgrade itself in place and needs CPU headroom to roll new pods next to the old ones; at 8 vCPU that rollout has been seen to wedge with the platform's own database unschedulable. Give the VM 12.

| Resource | Minimum | Recommended |
|---|---|---|
| Host CPU | 12 cores | 16 cores or more |
| Host RAM | 48 GiB | 64 GiB or more |
| Host disk, free | 160 GiB | 250 GiB |
| CRC VM | 10 vCPU, 28 GiB, 100 GiB | 12 vCPU, 32 GiB, 120 GiB |
| Hardware virtualisation | VT-x or AMD-V enabled in firmware | |
| Host OS | RHEL 9, registered | |

### Accounts and access

| Need | Where |
|---|---|
| Red Hat account with the OpenShift Local pull secret | console.redhat.com → OpenShift → Downloads → OpenShift Local |
| AAP subscription manifest, or a service account for connected activation | console.redhat.com → Subscriptions → Manifests; see [`AAP_SUBSCRIPTION_MANIFEST.md`](../../docs/install/AAP_SUBSCRIPTION_MANIFEST.md) |
| `registry.redhat.io` credentials | the Orchestrator and PostgreSQL images; the OpenShift Local pull secret already contains them |
| Outbound HTTPS from the host and the VM | console.redhat.com, registry.redhat.io, mirror.openshift.com, the Red Hat operator catalog |

### Placeholders

| Placeholder | Meaning |
|---|---|
| `<ao-db-password>` | the password you generate for the Orchestrator's database, in `manifests/40-ao-postgres.yaml` |

## 3. Prepare the host

```bash
sudo dnf install -y libvirt qemu-kvm libvirt-daemon-driver-storage libvirt-daemon-driver-network libvirt-client
sudo systemctl enable --now libvirtd
sudo usermod -aG libvirt,kvm "$USER"
```

CRC keeps the VM disk under `~/.crc/`. On RHEL, qemu runs as its own user by default and cannot read a disk image in your home directory, so make qemu run as the user that owns `~/.crc/`:

```bash
sudo bash -c "
grep -q '^user' /etc/libvirt/qemu.conf && sed -i 's|^#*user.*|user = \"$USER\"|' /etc/libvirt/qemu.conf || echo 'user = \"$USER\"' >> /etc/libvirt/qemu.conf
grep -q '^group' /etc/libvirt/qemu.conf && sed -i 's|^#*group.*|group = \"$USER\"|' /etc/libvirt/qemu.conf || echo 'group = \"$USER\"' >> /etc/libvirt/qemu.conf
grep -q '^dynamic_ownership' /etc/libvirt/qemu.conf && sed -i 's|^#*dynamic_ownership.*|dynamic_ownership = 0|' /etc/libvirt/qemu.conf || echo 'dynamic_ownership = 0' >> /etc/libvirt/qemu.conf
"
sudo systemctl restart libvirtd
```

Log out and back in so the group membership applies.

## 4. Install OpenShift Local

```bash
cd /tmp
curl -sSL -o crc.tar.xz "https://mirror.openshift.com/pub/openshift-v4/clients/crc/latest/crc-linux-amd64.tar.xz"
tar -xf crc.tar.xz
sudo install -m 0755 crc-linux-*-amd64/crc /usr/local/bin/crc
crc version

crc config set preset openshift
crc config set cpus 12
crc config set memory 32768
crc config set disk-size 120
crc config set consent-telemetry no
crc setup
```

Save the pull secret you downloaded as `~/.crc/pull-secret.txt` (mode 0600), then:

```bash
crc start --pull-secret-file ~/.crc/pull-secret.txt
```

The first start downloads the bundle and takes 10 to 20 minutes. End state: `crc status` reports OpenShift running. Set up the shell:

```bash
eval "$(crc oc-env)"
export KUBECONFIG=$HOME/.crc/machines/crc/kubeconfig
oc whoami            # kubeadmin or system:admin
crc console --credentials
```

**Port conflicts.** CRC binds 80, 443, 2222 and 6443 on the host. A rootless container already publishing any of those stops CRC from starting; stop it first.

**The cluster's DNS domain** is `apps-crc.testing`, served by CRC from the host's own resolver. Every route in this guide uses it. To reach the consoles from another machine on the network, point that machine's resolver for `apps-crc.testing` and `crc.testing` at the host (dnsmasq on the host is the usual way).

## 5. Install AAP 2.7

Two manifests. The first installs the operator from the Red Hat catalog on channel `stable-2.7`; the second creates the platform.

```bash
cd <checkout of this repository>
oc apply -f install/openshift-local/manifests/10-aap-operator.yaml
oc -n aap-operator get csv -w          # wait for aap-operator.v2.7.x  Succeeded, then Ctrl-C
oc apply -f install/openshift-local/manifests/20-aap.yaml
oc -n aap-operator get pods -w         # 15 to 25 minutes
```

`20-aap.yaml` enables the controller, EDA and Private Automation Hub, sets edge TLS on the routes, and leaves Lightspeed off. Edit it before applying if you want something else; every field is the operator's own.

### 5.1 Fix persistent volume permissions (CRC only)

CRC's hostpath provisioner creates volumes with mode 0755. The platform's PostgreSQL and the Hub's file storage need to write to them. After the first rollout, if `aap-postgres-15-0` or the `aap-hub-*` pods sit in `Init` or `CrashLoopBackOff`:

```bash
oc debug node/crc --quiet -- chroot /host bash -c 'for d in /var/lib/csi-hostpath-data/pvc-*; do chmod 777 "$d"; done'
oc -n aap-operator delete pod aap-postgres-15-0 --force --grace-period=0
oc -n aap-operator get pods --no-headers | awk '/aap-hub-/ && /Init|Crash/ {print $1}' | xargs -r oc -n aap-operator delete pod --force --grace-period=0
```

Wait a further five minutes for every pod to show Running. The same fix applies to the Orchestrator's PostgreSQL volume in section 7 if that pod fails to start.

### 5.2 Sign in and mint an API token

The operator generates the admin password into a Secret:

```bash
oc -n aap-operator get secret aap-admin-password -o jsonpath='{.data.password}' | base64 -d; echo
```

The UI is `https://aap-aap-operator.apps-crc.testing`, user `admin`. Change the password in the UI (Access Management → Users) if you want your own.

AAP 2.7 issues API tokens at the gateway. The Orchestrator connection in section 7 uses one:

```bash
HOST=aap-aap-operator.apps-crc.testing
read -rs -p "AAP admin password: " AAP_ADMIN_PASSWORD; echo
TOKEN=$(curl -sk -u "admin:$AAP_ADMIN_PASSWORD" -X POST -H 'Content-Type: application/json' \
  -d '{"description":"automation-orchestrator","scope":"write"}' "https://$HOST/api/gateway/v1/tokens/" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
unset AAP_ADMIN_PASSWORD
```

For anything beyond an evaluation, mint the token for a dedicated platform user with only the roles the Orchestrator's workflows need, not for `admin`. Keep the token in your shell or in a credential store, never in a file in the repository.

## 6. Entitle the platform

Without a subscription the controller refuses to create hosts. Upload the manifest in the UI (Settings → Subscription), or activate with a service account. The full procedure, including entitlement counts and what differs for customers, is [`AAP_SUBSCRIPTION_MANIFEST.md`](../../docs/install/AAP_SUBSCRIPTION_MANIFEST.md); CRC is its topology B, where the manifest is applied after deployment. Verify:

```bash
curl -sk -H "Authorization: Bearer $TOKEN" "https://$HOST/api/controller/v2/config/" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("license_info", {}).get("license_type", "none"))'
```

## 7. Install Automation Orchestrator

The Orchestrator operator brings no database: it requires a PostgreSQL you provide, holding two databases, one for the backend and one for Temporal. Three manifests: the database, the operator, the Orchestrator.

### 7.1 PostgreSQL for the Orchestrator

Generate a password and put it in the three places `manifests/40-ao-postgres.yaml` marks `<ao-db-password>` (the database pod's Secret and the two Secrets the Orchestrator reads):

```bash
PW=$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)
sed "s#<ao-db-password>#$PW#g" install/openshift-local/manifests/40-ao-postgres.yaml | oc apply -f -
unset PW
oc -n automation-orchestrator get pods -w     # ao-postgres Running
```

The image creates `ao_backend`; create the Temporal database beside it:

```bash
oc -n automation-orchestrator exec deploy/ao-postgres -- psql -U postgres -c "CREATE DATABASE ao_temporal OWNER ao;"
oc -n automation-orchestrator exec deploy/ao-postgres -- psql -U postgres -c "\l" | grep -E "ao_backend|ao_temporal"
```

If the pod stays in `CrashLoopBackOff` on first start, apply the volume permission fix from section 5.1 and delete the pod.

**Alternative.** When you install AAC afterwards, its PostgreSQL on the host can hold these two databases instead; set `spec.postgres.host` in `50-ao.yaml` to that host and the Secrets to its credentials. One database server is simpler to back up. For the evaluation, the in-cluster one above is enough.

### 7.2 Pull secret and operator

The Orchestrator images come from `registry.redhat.io`. The manifest references a pull secret named `redhat-registry-pull-secret` in the Orchestrator's namespace; create it from the same pull-secret file you gave CRC, which carries those credentials:

```bash
oc -n automation-orchestrator create secret generic redhat-registry-pull-secret \
  --from-file=.dockerconfigjson="$HOME/.crc/pull-secret.txt" --type=kubernetes.io/dockerconfigjson
```

Then the operator. It is cluster-scoped and subscribes in `openshift-operators`:

```bash
oc apply -f install/openshift-local/manifests/30-ao-operator.yaml
oc -n openshift-operators get csv -w     # automation-orchestrator-operator.v2026.x  Succeeded, then Ctrl-C
```

### 7.3 The Orchestrator

```bash
oc apply -f install/openshift-local/manifests/50-ao.yaml
oc -n automation-orchestrator get pods -w   # ao-backend, ao-ui, ao-worker, ao-background-worker, ao-temporal, ao-redis
oc -n automation-orchestrator get route ao
```

`50-ao.yaml` sets the Route host, the database connection, the pull secret, one Redis replica, a small worker autoscaler, and the **outbound allow list** `workflowHttpRequestAllowedHosts`. A workflow HTTP node may only call a host on that list. The platform's route and in-cluster Service name are listed; when the AAC workflows arrive they call the policy engine and an MCP server too, and those hosts go on the list then (the extended guide names them). Edit the CR with `oc edit automationorchestrator ao -n automation-orchestrator`; the operator reconciles the change.

### 7.4 First sign-in

The operator generates the initial administrator password into a Secret named after the resource:

```bash
oc -n automation-orchestrator get secret ao-initial-admin-password -o jsonpath='{.data.password}' | base64 -d; echo
```

Sign in at `https://ao-automation-orchestrator.apps-crc.testing` as `admin` and change the password. Create a project for your work; integrations and credentials below are created inside it or globally.

### 7.5 Connect the Orchestrator to the platform

In the Orchestrator UI:

1. **Credentials → Create**: an Ansible Automation Platform token credential holding the gateway token from section 5.2.
2. **Integrations → Create → Ansible Automation Platform**: URL `https://aap-aap-operator.apps-crc.testing`, select the credential. The route certificate is self-signed on CRC, so either paste the cluster router CA (`oc -n openshift-ingress-operator get secret router-ca -o jsonpath='{.data.tls\.crt}' | base64 -d`) into the integration's CA certificate field, or enable "skip TLS verification" for the evaluation only.
3. Validate: the integration lists the platform's organisations, inventories, job templates and workflow job templates. A workflow node of type "AAP job template" can now launch any of them.

Optional: the Orchestrator can register itself as an OAuth2 application on the platform so users sign in to the Orchestrator with their platform account (OIDC). That is a setting under the Orchestrator's authentication configuration; it needs the platform admin credentials once, at setup.

## 8. Verify

```bash
HOST=aap-aap-operator.apps-crc.testing
res() { curl -sk -H "Authorization: Bearer $TOKEN" -o /dev/null -w "$1 %{http_code}\n" "https://$HOST$2"; }
res "gateway    " /api/gateway/v1/ping/
res "controller " /api/controller/v2/ping/
res "eda        " /api/eda/v1/status/
curl -sk -o /dev/null -w "orchestrator %{http_code}\n" https://ao-automation-orchestrator.apps-crc.testing/
oc -n aap-operator get pods --no-headers | grep -vc Running
oc -n automation-orchestrator get pods --no-headers | grep -vc Running
```

Expected: 200 on the four endpoints and two zeros (no pod outside Running). Then, in the Orchestrator, create a one-node workflow that launches the platform's "Demo Job Template", publish it, execute it, and confirm the job appears in the controller's Jobs view. That is the whole loop: the Orchestrator decides, the platform acts.

## 9. Day-2 on CRC: what breaks after a restart

| After `crc stop` / `crc start` or a host reboot | What you see | Fix |
|---|---|---|
| `~/.kube/config` is rewritten | `oc` reports missing or incomplete configuration | `export KUBECONFIG=$HOME/.crc/machines/crc/kubeconfig` |
| The controller's project cache comes back owned by root | every job fails at elapsed 0 with no output and no job pod | `oc -n aap-operator delete pod -l app.kubernetes.io/name=automation-controller-task`; projects re-sync from git |
| The platform operator upgrades itself and needs CPU to roll new pods beside the old | pods Pending with `Insufficient cpu`, including the platform's own database | size the VM at 12 vCPU from the start; if it happens, scale a non-essential deployment to zero until the rollout completes |

Also:

- Never edit files under `/etc/containers` or `registries.conf` on the CRC node by hand; the machine config operator reports the node degraded indefinitely. Use `oc` to configure image sources.
- `crc status` can report the cluster degraded while every pod is Running, during CNI start-up; wait five minutes before acting on it.
- `crc delete` destroys everything in the VM, including the Orchestrator's database above. Export workflows from the Orchestrator before a rebuild, or keep its databases on the host PostgreSQL (section 7.1, alternative).

## 10. Next: Ansible Automated Compliance

Follow the [AAC extended install guide](../existing-aap/extended/README.adoc) from its first section. It assumes a running AAP, which you now have, and builds the compliance stack on the host beside the cluster. Three values it needs from this install:

| It asks for | Use |
|---|---|
| the platform hostname | `aap-aap-operator.apps-crc.testing` (its certificate is self-signed on CRC; trust the router CA from section 7.5 or set its verify flag off for the evaluation) |
| a platform token or admin credentials for its bootstrap | section 5.2 |
| the Orchestrator, for the governed workflows | section 7; add the policy engine and MCP hosts it names to `workflowHttpRequestAllowedHosts` in `50-ao.yaml` |

One CRC-specific point for that guide: the execution environment runs as pods inside the VM, so the host it installs the compliance stack on must be resolvable from inside the cluster by name, and the host firewall must admit the VM's network (libvirt `crc`, 192.168.130.0/24 by default) to the compliance ports. Test from a throwaway pod before running its bootstrap:

```bash
oc -n aap-operator run reach --rm -it --restart=Never --image=registry.access.redhat.com/ubi9/ubi-minimal -- curl -s -o /dev/null -w "%{http_code}\n" http://<aac-host>:8181/health
```

## 11. Known limitations

- One node, no high availability, self-signed certificates: an evaluation, not a production platform.
- Lightspeed is disabled in the shipped platform manifest; enabling it needs about 6 GiB more memory in the VM and a model endpoint.
- Event-Driven Ansible activations run inside the cluster and have no view of the host filesystem; file-watch and journald rulebooks are not available in this topology.
- The Orchestrator's file uploads are off (no S3-compatible storage is configured in `50-ao.yaml`); add `spec.fileStorage` if a workflow needs them.
- The shipped manifests were taken from the maintainers' AAP 2.7 and Orchestrator installs and verified against them; a customer team has not yet walked this guide end to end on a fresh host, and the support matrix says so.

## 12. References

- [`install/existing-aap/extended/README.adoc`](../existing-aap/extended/README.adoc) — Ansible Automated Compliance on the platform this guide installs
- [`docs/install/AAP_SUBSCRIPTION_MANIFEST.md`](../../docs/install/AAP_SUBSCRIPTION_MANIFEST.md) — entitling the platform
- [`install/SUPPORT_MATRIX.md`](../SUPPORT_MATRIX.md) — tiers and what has been exercised
- Red Hat documentation: OpenShift Local getting started; Ansible Automation Platform 2.7 on OpenShift (operator installation); Automation Orchestrator installation

---

*Co-authored by Claude (Anthropic).*
