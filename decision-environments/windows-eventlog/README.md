> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: RETIRED-HOSTx7, AAP-2.5/2.6x1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Decision Environment — `de-windows-eventlog`

Decision Environment for the Windows Golden Image Drift Watcher EDA activation.

## Why this DE exists

AAP 2.6's stock Default Decision Environment (`registry.redhat.io/ansible-automation-platform-26/de-supported-rhel9:latest`) doesn't ship `pywinrm`, so the `winrm_eventlog` event-source plugin can't import the `winrm` package. ansible-rulebook 1.1.x also doesn't reliably pick up project-bundled collections at activation runtime — the collection needs to be installed system-wide in the DE image.

This Containerfile fixes both:

1. `pip install pywinrm requests-ntlm` — gives the plugin the Python WinRM client it needs (and NTLM transport for corporate Windows hosts using `transport: ntlm`)
2. `COPY ... ansible_collections/lab → /usr/share/ansible/collections/...` — bakes the `lab.eda` collection (which wraps the `winrm_eventlog` plugin) onto the image so ansible-rulebook resolves `lab.eda.winrm_eventlog` by FQCN

## How to build

From a machine that has podman, the AAC repo cloned, and network reach to the AAP hub registry at `AAP_HOST`:

```bash
cd <repo-root>/decision-environments/windows-eventlog
./build.sh
```

Or manually:

```bash
cd <repo-root>
podman build -t AAP_HOST/de-windows-eventlog:latest \
  -f decision-environments/windows-eventlog/Containerfile .
podman push --tls-verify=false AAP_HOST/de-windows-eventlog:latest
```

The build context must include `collections/ansible_collections/lab` — that's why the COPY is `collections/...` (relative to repo root) and the Containerfile gets built from the repo root, not from this directory.

## How to register the DE in EDA

```bash
TOKEN=$(grep vault_aap_local_mcp_token ansible/vars/vault_secrets.yml | awk '{print $2}')
curl -sk -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  https://AAP_HOST/api/eda/v1/decision-environments/ \
  -d '{
    "name": "DE Windows EventLog",
    "description": "de-supported-rhel9 + pywinrm + lab.eda collection",
    "image_url": "AAP_HOST/de-windows-eventlog:latest",
    "organization_id": 1,
    "eda_credential_id": 3
  }'
```

(`eda_credential_id: 3` is the existing "Hub Decision Environment Container Registry" credential that lets EDA pull from the AAP hub registry.)

## How to create an activation using this DE

Through the EDA UI:
- Rulebook: `extensions/eda/rulebooks/windows_golden_enforcement.yml`
- Decision Environment: `DE Windows EventLog`
- Credentials: `AAP Controller Token (Sentinel Demo)`
- Variables (paste as YAML):
  ```yaml
  windows_host_ip: <current public IP of compliance-lab-windows2022>
  windows_admin_user: Administrator
  windows_admin_password: <pull vault_windows_admin_password from ansible/vars/vault_secrets.yml>
  ```

The plugin will poll WinRM every 10 seconds, watching for event IDs 5007 (Defender real-time change), 2003 (Firewall settings change), 7036 (service state change), 4719 / 4956 (audit policy changes).

## Verifying the build worked

```bash
podman run --rm AAP_HOST/de-windows-eventlog:latest \
  python3 -c "import winrm; print('pywinrm', winrm.__version__)"

podman run --rm AAP_HOST/de-windows-eventlog:latest \
  ls /usr/share/ansible/collections/ansible_collections/lab/eda/plugins/event_source/
```

Expected:
- `pywinrm 0.5.0` (or later)
- `winrm_eventlog.py` listed
