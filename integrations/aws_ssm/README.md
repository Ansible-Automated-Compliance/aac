# AWS SSM (Systems Manager)

## At a glance

- **Customer system:** AWS Systems Manager — Session Manager, RunCommand, Patch Manager, Parameter Store, State Manager
- **AAC pattern:** push from AAC (issue SSM commands) — replaces SSH for managed EC2 fleets
- **Status in AAC today:** ⚠ partial — `amazon.aws` 8.0+ is in our EE (has `ssm_*` modules) but no AAC playbooks use SSM yet; the existing AAC managed-host pattern is direct SSH
- **Effort estimate:** TBD — pending write-up
- **Required collections:**
  - `amazon.aws` v11.3.0 (Galaxy + Automation Hub certified) — EE currently has 8.0+. Modules: `amazon.aws.ssm_inventory`, `amazon.aws.aws_ssm` connection plugin
  - `community.aws` v11.0.0 — older SSM modules not yet migrated
- **Customer-side prerequisites:**
  - SSM Agent installed on every managed EC2 (Amazon Linux + recent RHEL AMIs have it pre-installed)
  - IAM instance profile granting `AmazonSSMManagedInstanceCore` on each EC2
  - For AAC service: cross-account IAM role with `ssm:SendCommand`, `ssm:GetCommandInvocation`, `ssm:DescribeInstanceInformation`
  - VPC endpoints for SSM (avoid NAT gateway egress for management traffic)

## Customer use case (1-sentence summary)

Customer's EC2 fleet is managed via AWS SSM (no inbound SSH from corp
network). AAC's compliance assessments run via `aws_ssm` connection
plugin (or `amazon.aws.aws_ssm_session`) instead of direct SSH, so the
existing CIS / STIG playbooks work against EC2s in private subnets
without VPN, bastion, or SSH key distribution.

## Status

📝 **Pending full write-up.**

## Quick notes (for the eventual write-up)

- **Connection plugin swap is the big win:** Ansible's `aws_ssm` connection plugin lets existing playbooks (`ansible/playbooks/cis_*_assessment.yml` etc.) run against SSM-managed hosts with no code changes. Just change the inventory's `ansible_connection: aws_ssm`.
- **Dynamic inventory:** `amazon.aws.aws_ec2` already in use (`ansible/inventory/aws_ec2.yml`). Add `compose: ansible_aws_ssm_bucket_name: ...` to switch matching hosts to SSM transport.
- **Existing AAC pattern overlap:**
  - `ansible/playbooks/aws_provision_compliance_lab.yml` provisions a lab EC2 today via SSH; would switch to SSM-style
  - `ansible/roles/aac_facts_collector/tasks/aws_metadata.yml` already queries EC2 metadata — SSM gives us much more (host-level inventory at zero extra cost)
- **SSM Patch Manager parallel:** customers using SSM Patch Manager have an existing patch pipeline. AAC's CVE work (`integrations/_examples/servicenow_itsm.md` adjacent — actually `ansible/playbooks/aac_cve_*.yml`) should interoperate: AAC detects the CVE, optionally creates an SSM Patch Baseline or triggers a one-off Patch operation.
- **State Manager associations:** customers can store AAC playbooks as SSM Associations and have SSM (not AAP) schedule them on the fleet. Hybrid — AAP is still the canonical source of truth for playbook content but SSM handles cadence + targeting at fleet scale. Worth a sidebar in the write-up.
- **Parameter Store overlap with HVE:** if customer uses both HashiCorp Vault AND Parameter Store, decide which is canonical for which secret class. See [`../hashicorp_vault_enterprise/`](../hashicorp_vault_enterprise/).
- **Cross-account:** typical enterprise has many AWS accounts. AAC's IAM role assumption pattern needs to be in place (`STS AssumeRole` for each target account). `community.aws.sts_assume_role` covers this.
- **No EDA pattern needed in most cases** — SSM is pull from EC2 side; no inbound webhook surface for AAC. CloudWatch Events → EventBridge → AAC webhook is possible but rarely needed.

## See also

- [`../terraform_enterprise/`](../terraform_enterprise/) — TFE provisions EC2, SSM manages them, AAC scans them. Common cloud-Ops stack.
- [`../kubernetes_capi/`](../kubernetes_capi/) — for EC2-backed CAPI clusters (CAPA), the worker nodes are SSM-managed too
- `ansible/inventory/aws_ec2.yml` — existing AWS dynamic inventory
- `ansible/playbooks/aws_*.yml` — existing AWS lifecycle playbooks
- [`../_common/patterns.md`](../_common/patterns.md) — § 2 (Push from AAC)
- AWS SSM docs: https://docs.aws.amazon.com/systems-manager/
- `amazon.aws.aws_ssm` connection plugin: https://galaxy.ansible.com/ui/repo/published/amazon/aws/
