# Customer Integration Discovery Checklist

Half-page of questions to ask a customer in the early-scoping call. The
answers determine which `integrations/<slug>/` write-ups apply and what
order to land them in.

Run through these in order. Skip a section if the customer doesn't
have that category of system. Capture answers in your customer
engagement notes (NOT in this repo's committed files).

---

## 1. ITSM / ticketing

- Which ITSM platform? **ServiceNow / Jira / BMC Remedy / Cherwell / other / none**
- Production instance URL?
- Sandbox / dev instance URL? (almost always required for integration testing)
- Service-account creation policy? (do they create per-integration accounts, or share one?)
- Custom CIs / fields in CMDB that AAC should map to?
- For ServiceNow: incident table or change-request table? (AAC default is `incident` for drift)
- For Jira: which project key? Which issue type? Which severity field mapping?

## 2. Alert routing / on-call

- Alert aggregation platform? **BigPanda / Moogsoft / PagerDuty / Splunk On-Call / OpsGenie / none**
- On-call / paging platform? **xMatters / PagerDuty / VictorOps / OpsGenie / Squadcast / none**
- How is severity escalated? (P1/P2/P3 scheme, time-to-respond, page reconciliation)
- Do they want AAC events flowing into the aggregator (for noise reduction), or directly to the pager (for immediate action)?

## 3. SIEM / observability

- Which SIEM? **Splunk / Sentinel / Elastic / QRadar / Chronicle / Datadog / none**
- Forward via HEC / syslog / agent / API?
- Index destination + retention policy?
- Need separate index per compliance framework, or single AAC index?
- Existing CIM / ECS / OCSF schema in use?

## 4. Identity / authentication

- Primary IdP? **Active Directory / Azure AD (Entra) / Okta / Ping / Auth0 / FreeIPA / other**
- For AAP UI: federation via SAML / OIDC / LDAP?
- AAC playbooks need to query AD? (for group membership, computer object enumeration)
- Kerberos / GSSAPI required for any managed host? (typically Windows hosts)
- For RBAC: do they want AAP teams synced from AD groups, or maintained separately?

## 5. Secrets / credentials

- Centralized secrets store? **HashiCorp Vault Enterprise / HashiCorp Vault OSS / CyberArk / AWS Secrets Manager / Azure Key Vault / GCP Secret Manager / Ansible Vault only / none**
- For Vault: are credentials already exposed to AWX via Credential Plugin? (often yes — verify)
- Service account creation flow: self-service vs IT ticket vs Vault auth backend?
- Rotation policy + how customer wants AAC to handle rotation events?

## 6. Cloud + IaC

- Which cloud(s)? **AWS / Azure / GCP / OCI / on-prem-only**
- IaC tool? **Terraform Enterprise / Terraform OSS / OpenTofu / Pulumi / CloudFormation / Bicep / Ansible-only / none**
- Existing landing-zone tooling? (Control Tower, Azure Blueprints, etc.)
- For Terraform Enterprise: which workspaces does AAC interact with? (compliance-policy workspaces, infra workspaces, both)
- Sentinel / OPA policies already in use? (overlap with AAC's OPA)

## 7. Compute provisioning

- Where do new hosts come from? **CAPI (which provider — AWS / Azure / OCP / bare metal via Metal3) / Terraform / OpenStack / cloud-native auto-scaling / manual**
- Bare metal? **Metal3 / Foreman / MAAS / iPXE / OpenStack Ironic standalone / none**
- For EC2: do they use AWS SSM Session Manager exclusively, or also SSH directly?

## 8. Compliance frameworks + regulatory drivers

- Which compliance frameworks drive this engagement? (NERC-CIP / PCI-DSS / HIPAA / FedRAMP / SOX / ISO 27001 / DORA / SOC 2 / multiple)
- Specific controls highlighted by recent audit findings?
- Continuous compliance vs point-in-time attestation?
- Evidence-of-compliance reporting format? (PDF / Excel / API to a GRC tool)
- Sentinel-based git policy gating already in use?

## 9. Network / topology

- AAC + AAP topology: single-AAP node / clustered / multi-region / DR-paired?
- Air-gapped network segments AAC needs to reach? (which integrations are in vs. out of the air-gap zone)
- IPv6-only segments?
- Proxy requirements? (HTTP_PROXY for outbound API calls)
- mTLS required between AAC and any vendor system?

## 10. Operational readiness

- Backup / DR strategy for the AAC compliance DB?
- Customer's incident-response runbook — does AAC integration need to feed into it?
- Change-management cadence: how often can AAC's playbooks be updated in production? (drives CI/CD and Sentinel gating need)
- On-call ownership: who answers the page if an EDA activation crash-loops at 3am?

---

## Output of this conversation

After running through this with the customer, produce:

1. **An integration list** — which `integrations/<slug>/` write-ups apply
2. **A priority order** — which integration unlocks the highest-value compliance use case for them
3. **Per-integration credential / endpoint asks** — what you need from the customer-side IT team before kickoff
4. **A risk log** — anything in the answers above that breaks the standard pattern (air-gapped, proxy, custom SAML, etc.)

Feed all four into the customer engagement project plan.
