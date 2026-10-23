# Install AAC on an Existing AAP

**Version:** v2.0
**Applies to:** AAP 2.6 or later (2.7 in the lab)
**Estimated time:** 2–4 hours for a careful first install

Adds the full AAC compliance stack to an AAP instance you already run. No provisioning —
this assumes AAP is up and your target hosts are reachable.

> **This guide is the production-oriented path**, reconciled with what has actually been
> followed on a customer install. Where lab practice and customer practice differ — secrets
> handling above all — both are given, and which is which is stated explicitly.

---

## 1. What you get

- OPA containers (`opa-security`, `opa-compliance`, `opa-ot`)
- Rego policies loaded from the `policies/` submodule
- A dedicated AAC PostgreSQL database
- Grafana dashboards
- An AAP project + job templates
- An Execution Environment
- Optional, encouraged: EDA and the MCP server (§9)

## 2. Architecture recommendation

**Prefer a dedicated AAC host.** It gives clear blast radius, its own capacity, and
unambiguous container naming. Do not put AAC containers on the AAP host — you risk AAP's
data and collide on container names.

## 3. Prerequisites

- AAP 2.6 or later (controller + gateway; EDA if you take §9)
- RHEL host for `aac_host`, registered to Red Hat
- Outbound HTTPS to GitHub, `console.redhat.com`, `registry.redhat.io`
- Firewall capacity for the AAC ports (§7.6)

## 4. Process

1. AAC host setup → 2. Repository checkout → 3. Secrets → 4. OPA → 5. PostgreSQL →
6. Rego policy loading → 7. Grafana → 8. Quadlets → 9. AAP project + EE →
10. Verification → 11. First assessment

---

## 5. AAC host setup

### 5.1 Basic requirements

RHEL server with a `compliance` user, registered to Red Hat.

```bash
ssh compliance@<aac-host>
echo "compliance ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/compliance
sudo dnf install -y podman ansible-core vim tree jq curl pip bash-completion
sudo dnf upgrade -y && sudo systemctl reboot
mkdir -p ~/repos/
```

### 5.2 Repository checkout

```bash
cd ~/repos/
git clone https://github.com/ansible-automated-compliance/aac.git
# or: git clone https://github.com/ansible-automated-compliance/aac.git
cd compliance
git submodule update --init --recursive
tree -L 2 policies/benchmarks/
```

If you use SSH, generate a key and register it with GitHub:

```bash
ssh-keygen -t ed25519 -C "compliance@<aac-host>"
cat ~/.ssh/id_ed25519.pub
```

---

## 6. Secrets

```bash
cp ansible/vars/vault_secrets.yml.example ansible/vars/vault_secrets.yml
vim ansible/vars/vault_secrets.yml
```

Populate the placeholders — Red Hat username and offline token, GitHub PAT, Quay
credentials, AAP admin password, database and Grafana passwords.

> **Credentials are not inherited by every template in a project.** Attach them per job
> template.

### 6.1 Vault encryption — lab and customer are different, deliberately

| | Practice | Why |
|---|---|---|
| **Lab** | `vault_secrets.yml` left as **plaintext YAML** | Convenience while iterating. The `ansible-vault` CLI does not work against the lab copy, and repo docs describing it as plaintext are describing the lab |
| **Customer install** | **Encrypt it.** `ansible-vault encrypt ansible/vars/vault_secrets.yml` | Real credentials at rest on a customer host |

**For any customer install, encrypt.** Every `ansible-playbook` invocation below then needs a
vault password — `-J` to be prompted, or `--vault-password-file`:

```bash
ansible-vault encrypt ansible/vars/vault_secrets.yml
```

Do not carry the lab's plaintext convention into a customer environment.

### 6.2 CAA signing key

Required for CIS playbooks that enable CAA. Generate with the `cosign` binary from a
container:

```bash
cid=$(podman create <cosign-image>)     # see note
podman cp "$cid":/usr/bin/cosign ./cosign
podman rm "$cid"
chmod +x ./cosign
COSIGN_PASSWORD="" ./cosign generate-key-pair
```

> **Verify the image reference before running this.** The install guide this was reconciled
> against cites `registry.access.redhat.com/hi/cosign:3`; `hi` is not a Red Hat namespace we
> use anywhere else in this repo, and no cosign image is referenced elsewhere. Confirm the
> correct Trusted Artifact Signer image rather than copying that string.

Put the private key and its password into `vault_secrets.yml` as `caa_signing_private_key`
and `caa_signing_password`.

> **The public key is for auditors** (`cosign verify-blob`). Do not inject it as the signing
> secret on a job template.

### 6.3 Container secrets (podman)

So passwords never appear in `podman run` arguments or in process listings:

```bash
printf 'compliance'     | podman secret create compliance_db_password -
printf 'compliance'     | podman secret create compliance_reader_password -
printf '<grafana-admin-password>' | podman secret create grafana_admin_password -
podman secret list
```

Rotating one later:

```bash
podman secret rm compliance_db_password
printf 'new_password' | podman secret create compliance_db_password -
```

---

## 7. AAC stack

### 7.1 Directories

```bash
sudo mkdir -p /etc/opa/compliance
sudo chown -R compliance:compliance /etc/opa
```

### 7.2 OPA containers

```bash
ansible-playbook -J ansible/playbooks/deploy_opa_containers.yml \
  -e "aac_host=<aac-host>" -e "become_user=root" \
  -e "become=true" -e "become_method=sudo"
```

Verify — expect HTTP 200 / JSON from each:

```bash
for p in 8181 8182 8183; do curl -s http://<aac-host>:$p/health; echo; done
```

| Container | Port | Frameworks |
|---|---|---|
| `opa-security` | 8181 | CIS benchmarks, NIST, STIGs |
| `opa-compliance` | 8182 | ISO 27001, SOC 2, PCI-DSS, SOX, FISMA, GDPR, … |
| `opa-ot` | 8183 | NERC-CIP, IEC 62443, AMI / NIST IR 7628 |

### 7.3 PostgreSQL

```bash
podman volume create compliance_pgdata
podman run -d --name aac-postgresql \
  -p 5432:5432 \
  -e POSTGRESQL_USER=compliance \
  -e POSTGRESQL_DATABASE=compliance \
  --secret compliance_db_password,type=env,target=POSTGRESQL_PASSWORD \
  -v compliance_pgdata:/var/lib/pgsql/data \
  --restart=always \
  registry.redhat.io/rhel9/postgresql-15:latest
```

Initialise the schema:

```bash
pip3 install --user psycopg2-binary
ansible-galaxy collection install community.postgresql

ansible-playbook -J ansible/playbooks/postgres_database_init.yml \
  -e "aac_host=<aac-host>" -e "pg_host=<aac-host>" -e "pg_user=compliance" \
  -e "aac_db_container_name=aac-postgresql" -e "aac_db_skip_container_deploy=true"
```

> **On the `compliance_reader` role.** `CREATE ROLE` requires the connecting user to hold
> SUPERUSER or CREATEROLE, and the RHEL postgresql image grants `POSTGRESQL_USER` neither.
> Connecting as `compliance` therefore cannot create it. **This is not safe to skip** — the
> Customer Portal reads this database *as* `compliance_reader`. The playbook now checks the
> privilege up front and states the remedy; take one of the options it prints (connect as a
> superuser for this step, grant `CREATEROLE` once, or create the role by hand) and re-run.
> The grants are idempotent.

Verify:

```bash
podman exec -it aac-postgresql psql -U compliance -d compliance -c "\dt"
```

### 7.4 Load the Rego policies

The health curls in §7.2 are **not** the load step. An empty `{"result":[]}` after deploy is
normal until this runs.

```bash
ansible-galaxy collection install amazon.aws

ansible-playbook -J ansible/playbooks/load_opa_policies.yml \
  -e "opa_security_url=http://<aac-host>:8181" \
  -e "opa_compliance_url=http://<aac-host>:8182" \
  -e "opa_ot_url=http://<aac-host>:8183"
```

Verify:

```bash
for p in 8181 8182 8183; do curl -s http://<aac-host>:$p/v1/policies | jq '.result | length'; done
```

**Count the expected total rather than trusting a figure in a document** — it moves with every
submodule bump, and stale numbers have propagated through these docs before:

```bash
PINNED=$(git ls-tree HEAD policies | awk '{print $3}')
git -C policies ls-tree -r "$PINNED" --name-only \
  | grep '\.rego$' | grep -vcE '(^|/)(test_|.*_test\.rego$)'
```

### 7.5 Grafana

```bash
podman volume create compliance_grafanadata
podman run -d --name aac-grafana \
  -p 3000:3000 --restart=always \
  -v compliance_grafanadata:/var/lib/grafana \
  -e GF_SECURITY_ADMIN_USER=admin \
  --secret grafana_admin_password,type=env,target=GF_SECURITY_ADMIN_PASSWORD \
  -e GF_SERVER_HTTP_ADDR=0.0.0.0 -e GF_SERVER_PORT=3000 \
  -e GF_SERVER_ROOT_URL=http://<aac-host>:3000 \
  -e GF_INSTALL_PLUGINS=grafana-postgresql-datasource \
  registry.redhat.io/rhel9/grafana:latest
```

> `GF_SECURITY_ADMIN_PASSWORD` only takes effect on **first** initialisation against an empty
> database. If you recreate the container and login fails, delete the volume first.

Then configure the datasource and import dashboards — this playbook does **not** start
Grafana, it configures an existing one on `:3000`:

```bash
ansible-playbook -J ansible/playbooks/deploy_grafana_dashboard.yml \
  -e "grafana_url=http://<aac-host>:3000" -e "pg_host=<aac-host>"
```

### 7.6 Firewall

```bash
for port in 3000 5432 8181 8182 8183; do
  sudo firewall-cmd --permanent --add-port=${port}/tcp
done
sudo firewall-cmd --reload
```

> **Do not open 5432** if AAP reaches Postgres on a private interface.

Add `5000–5004` (EDA webhooks) and `8004` (MCP) only if you take §9.

### 7.7 Quadlets — make the stack survive a reboot

Hand-started containers do not come back. Quadlets put them under systemd on the user bus.

Remove the system units first, as root, once:

```bash
sudo systemctl disable --now container-opa-security.service \
  container-opa-compliance.service container-opa-ot.service
sudo rm -f /etc/systemd/system/container-opa-*.service \
  /etc/systemd/system/container-aac-postgresql.service \
  /etc/systemd/system/container-aac-grafana.service
sudo systemctl daemon-reload
```

Then as `compliance`, install the Quadlet units and let systemd own the containers:

```bash
mkdir -p ~/.config/containers/systemd/
# copy the unit files from the repo's quadlets directory into that path
podman rm -f opa-security opa-compliance opa-ot aac-postgresql aac-grafana

systemctl --user daemon-reload
systemctl --user start opa-security opa-compliance opa-ot aac-postgresql aac-grafana
systemctl --user is-active opa-security opa-compliance opa-ot aac-postgresql aac-grafana
```

Survive logout and reboot without an interactive login:

```bash
loginctl enable-linger compliance
loginctl show-user compliance -p Linger
systemctl --user --failed
```

---

## 8. AAP integration

### 8.1 Project

AAP UI → **Projects → Add**

- **Source Control URL:** `https://github.com/ansible-automated-compliance/aac`
- **Credential:** GitHub PAT (Source Control)
- **Branch:** `main`
- Enable update-on-launch as required, and ensure submodules initialise (`policies/`)

### 8.2 Credentials

| Name | Type | Purpose |
|---|---|---|
| Compliance SSH Credential | Machine | SSH to target hosts |
| Ansible Vault | Vault | Vault password (required once §6.1 encryption is applied) |
| GitHub PAT | Source Control | Project sync |

### 8.3 Build and push the Compliance EE

```bash
cd install/existing-aap/ee
podman login registry.redhat.io
ansible-builder build -v -f execution-environment.yml \
  --container-runtime podman -t <registry>/aac-compliance-ee:latest
podman login <registry>
podman push <registry>/aac-compliance-ee:latest
```

### 8.4 First assessment

Launch `ansible/playbooks/cis_rhel9_assessment.yml` from the AAP UI. Expect a `policy_name`
of `CIS RHEL 9` to appear in the Grafana **AAC Infrastructure Compliance** dashboard.

---

## 9. Optional, and encouraged: EDA and MCP

Neither is required for a first production cut, and leaving them out keeps the initial
install smaller. Both are **encouraged** once the base stack is proven — EDA is what turns
AAC from scheduled assessment into drift detection with automatic enforcement, and MCP is
what exposes AAP to AI tooling under OPA governance.

Add ports `5000–5004` and `8004` to the firewall when you take them.

---

## 10. Verification checklist

| Check | Expected |
|---|---|
| `curl http://<aac-host>:{8181,8182,8183}/health` | HTTP 200 on all three |
| `curl .../v1/policies \| jq '.result \| length'` | Non-zero on all three; total matches the count command in §7.4 |
| `psql -U compliance -d compliance -c "\dt"` | Schema tables present |
| `compliance_reader` role exists | `\du` lists it — see the §7.3 note if it does not |
| `curl http://<aac-host>:3000/api/health` | Grafana healthy |
| `systemctl --user is-active` (§7.7) | All five active |
| `loginctl show-user compliance -p Linger` | `Linger=yes` |
| AAP project sync | Successful, submodule populated |
| First assessment | Rows in `compliance_results`, visible in Grafana |
