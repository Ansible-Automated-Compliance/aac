> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: RETIRED-HOSTx3, AAP-2.5/2.6x1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# AAC Fresh Install Pipeline — Status & Lessons Learned

> **⚠️ HISTORICAL DOCUMENT — April 2026**
>
> The fresh install was completed on **2026-03-28**. AAP 2.6 is live on AAP_HOST. The EC2 provisioning issue documented below was the last blocker and has since been resolved.
> Template IDs 86-93 listed in this document are from the pre-install seeding pipeline and no longer match the live AAP instance — see `CLAUDE.md` for current template IDs.
> The remainder of this document is preserved as a historical record of the pipeline build and the lessons learned.

**Last Updated:** 2026-04-17
**Status:** ✅ COMPLETED — Fresh install on AAP_HOST finished 2026-03-28

---

## What Works ✅

### Pipeline Playbooks (all committed to git, main branch)
All 8 playbooks are in `ansible/playbooks/`:

| File | Status |
|------|--------|
| `fresh_install_00_teardown.yml` | ✅ Working — terminates EC2, removes SG |
| `fresh_install_01_provision_ec2.yml` | ⚠️ Fails at `ec2_instance` launch (see below) |
| `fresh_install_02_prepare_os.yml` | Not yet tested |
| `fresh_install_03_verify_bundle.yml` | Not yet tested |
| `fresh_install_04_install_aap.yml` | Not yet tested |
| `fresh_install_05_install_aac.yml` | Not yet tested |
| `fresh_install_06_validate.yml` | Not yet tested |
| `seed_fresh_install_templates.yml` | ✅ Working |

### AAP Job Templates (all live on AAP_HOST)
Seed template creates all 7 pipeline templates:

| ID | Name | Credentials |
|----|------|-------------|
| 86 | AAC - Seed Fresh Install Templates | Ansible Vault |
| 87 | AAC - Fresh Install: 00 Teardown | Ansible Vault, AWS Compliance Lab |
| 88 | AAC - Fresh Install: 01 Provision EC2 | Ansible Vault, AWS Compliance Lab, Compliance SSH |
| 89 | AAC - Fresh Install: 02 Prepare OS | Ansible Vault, Compliance SSH |
| 90 | AAC - Fresh Install: 03 Verify Bundle | Ansible Vault, Compliance SSH |
| 91 | AAC - Fresh Install: 04 Install AAP | Ansible Vault, Compliance SSH |
| 92 | AAC - Fresh Install: 05 Install AAC | Ansible Vault, Compliance SSH |
| 93 | AAC - Fresh Install: 06 Validate | Ansible Vault, Compliance SSH |

### Design Decisions That Are Correct
- AWS credentials come from AAP credential ID 5 (AWS Compliance Lab) via env vars — NOT from vault_secrets.yml (which has PLACEHOLDERs for AWS keys)
- `registry.redhat.io` authentication uses `vault_redhat_offline_token` as the password (not an account password)
- RHSM subscription password is a **survey variable** (`rhsm_password`) on Phase 02 — not stored in vault
- Vault password for Phase 05 is also a **survey variable** (`vault_password`) — same pattern
- All playbooks use `hosts: localhost, connection: local` with `delegate_to: "{{ target_host }}"` for remote tasks

### Launch Format for Survey Variables
AAP Controller API requires survey vars in `extra_vars` (not under a `survey_vars` key):
```bash
curl -X POST .../job_templates/88/launch/ \
  -d '{"extra_vars": {"ec2_key_name": "compliance-lab-key", "aws_region": "us-east-1"}}'
```

---

## Open Issue: Phase 01 EC2 Launch Fails ⚠️

### Error
```
InvalidParameterCombination: The specified instance type is not eligible for Free Tier.
```
This error message from AWS is **misleading** — the real issue is a parameter combination problem with the `amazon.aws.ec2_instance` module.

### What Was Tried
1. Initial version: used `network: assign_public_ip: true` (deprecated) + explicit `aws_access_key/secret_key` → failed (credentials were PLACEHOLDER in vault)
2. Removed explicit AWS key params, relied on env vars from AWS credential → still failed (different reason: `network` + `security_group` conflict)
3. Added VPC/subnet lookup, used `network_interfaces` with `security_group` at top level → still failed (InvalidParameterCombination — can't mix top-level security_group with network_interfaces)
4. Switched to `vpc_subnet_id` + `security_groups` (list) + `network: assign_public_ip: true` → still failing (not yet tested after last sync)

### Next Steps to Investigate
The `network: assign_public_ip: true` parameter combined with `vpc_subnet_id` + `security_groups` may STILL trigger `InvalidParameterCombination`. The deprecation warning suggests using `network_interfaces` — but that requires moving security groups INTO the NI config (remove from top level entirely):

```yaml
# Try this approach next session:
- name: Launch RHEL 9 t3.2xlarge instance
  amazon.aws.ec2_instance:
    name: "{{ instance_name }}"
    key_name: "{{ ec2_key_name }}"
    instance_type: "{{ instance_type }}"
    image_id: "{{ rhel9_ami_id }}"
    region: "{{ aws_region }}"
    vpc_subnet_id: "{{ default_subnet_id }}"
    volumes:
      - device_name: /dev/sda1
        ebs:
          volume_size: "{{ root_volume_gb }}"
          volume_type: gp3
          delete_on_termination: true
    state: running
    wait: true
    wait_timeout: 300
    tags:
      Name: "{{ instance_name }}"
      Project: "aac"
      Purpose: "fresh-install-test"
      DestroyAfterValidation: "true"
    network_interfaces:
      - device_index: 0
        subnet_id: "{{ default_subnet_id }}"
        groups:
          - "{{ aac_sg.group_id }}"
        associate_public_ip_address: true
        delete_on_termination: true
```
Key: use `aac_sg.group_id` (the SG ID, not name), `associate_public_ip_address` (not `assign_public_ip`), and `device_index: 0`.

### Alternative: Use AWS CLI Directly
If the Ansible module continues to be problematic, consider an `ansible.builtin.shell` task running `aws ec2 run-instances` directly — more verbose but more predictable.

---

## Infrastructure Notes

### vault_secrets.yml in Git
The file at `ansible/vars/vault_secrets.yml` is tracked in git as **plaintext** with:
- AWS keys: PLACEHOLDER (real keys are in AAP credential ID 5)
- `vault_aap_local_mcp_token`: current MCP token (must be updated when token rotates)
- `vault_redhat_offline_token`: PLACEHOLDER (real token is in AAP credential ID 8 / Ansible Vault)

After a project sync, the AAP server file is **overwritten** with the git version.

### Security Group Cleanup
The teardown playbook (template 87) cleans up the `aac-fresh-install-sg` security group.
Run it with `instance_id: i-0000000000000000` to skip the terminate step and only clean the SG.

---

## Run Order (when Phase 01 is fixed)

1. **Template 88** — Phase 01: Provision EC2
   - Survey: `ec2_key_name=compliance-lab-key`, `aws_region=us-east-1`
   - Note the output: `instance_id` and `target_ip`

2. **Manual** — SCP files from Mac to target:
   ```bash
   scp ~/Downloads/ansible-automation-platform-containerized-setup-bundle-2.6-1-x86_64.tar.gz \
       ec2-user@<TARGET_IP>:/home/ec2-user/aap-bundle.tar.gz
   scp ~/Downloads/0ec418ab-59ed-4654-8ca9-de11cc57c0ce.zip \
       ec2-user@<TARGET_IP>:/home/ec2-user/aap-manifest.zip
   ```

3. **Template 89** — Phase 02: Prepare OS
   - Survey: `target_host=<TARGET_IP>`, `rhsm_password=<RH account password>`
   - Runtime: ~10-15 min

4. **Template 90** — Phase 03: Verify Bundle
   - Survey: `target_host=<TARGET_IP>`

5. **Template 91** — Phase 04: Install AAP (30-60 min — do NOT cancel)
   - Survey: `target_host`, `new_aap_admin_password`, `new_pg_password`

6. **Template 92** — Phase 05: Install AAC (~15-20 min)
   - Survey: `target_host`, `new_aap_admin_password`, `vault_password`

7. **Template 93** — Phase 06: Validate
   - Survey: `target_host`, `new_aap_admin_password`
   - Must show GO (all checks pass) before teardown

8. **Template 87** — Phase 00: Teardown
   - Survey: `instance_id=<from Phase 01>`, `aws_region=us-east-1`
