# Framework coverage, measured

> **Generated** by `scripts/framework_coverage.py --write`. Do not edit by hand.

Policy library pin: `3d3976e8`. Of 107 catalog keys, **101 return a report with a control count**, 6 return a report without one, and 0 resolve to nothing.

"Controls evaluated" is the module's own `total_controls` on empty input: the number of controls it evaluates. It is not a statement about how many controls the published standard contains.

| Key | Catalog entry | OPA service | Controls evaluated | Standard as the module names it |
|---|---|---|---|---|
| `bsi_c5` | BSI C5:2020 | compliance | 168 | BSI C5:2026 |
| `ccpa` | CCPA/CPRA | compliance | 7 | California Consumer Privacy Act (CCPA / CPRA) |
| `cfr_part_11` | 21 CFR Part 11 | compliance | 43 | FDA 21 CFR Part 11 |
| `cmmc` | CMMC 2.0 | compliance | 110 |  |
| `coppa` | COPPA | compliance | 21 | COPPA (Children's Online Privacy Protection Rule) |
| `csa_ccm` | CSA Cloud Controls Matrix v4.0 | compliance | 197 | Cloud Security Alliance Cloud Controls Matrix (CSA CCM) |
| `digital_sovereignty` | Digital Sovereignty Framework | compliance | 140 | Digital Sovereignty Assessment |
| `dora` | DORA (Digital Operational Resilience Act) | compliance | 399 | EU Digital Operational Resilience Act (DORA) |
| `eu_ai_act` | EU AI Act | compliance | 5 | EU Artificial Intelligence Act |
| `fedramp` | FedRAMP Authorization | compliance | 12 | FedRAMP |
| `ferpa` | FERPA | compliance | 32 | FERPA (Family Educational Rights and Privacy Act) |
| `fisma` | FISMA / FedRAMP Readiness | compliance | 7 |  |
| `gdpr` | GDPR | compliance | 4 | GDPR (EU) 2016/679 — Full Compliance Assessment |
| `hipaa` | HIPAA Security Rule | compliance | 246 | HIPAA Administrative Simplification (45 CFR Parts 160, 162, 164) + HITECH Act |
| `hitrust` | HITRUST CSF r2 | compliance | 59 | HITRUST Common Security Framework (CSF) |
| `iso27001` | ISO/IEC 27001:2022 | compliance | 93 | ISO/IEC 27001:2022 |
| `iso27701` | ISO/IEC 27701:2019 (PIMS) | compliance | 134 | ISO/IEC 27701 Privacy Information Management System |
| `ncsc_caf` | NCSC CAF 4.0 | compliance | 23 | NCSC Cyber Assessment Framework 4.0 |
| `nis2` | NIS2 Directive | compliance | 35 | EU Network and Information Security Directive 2 (NIS2) |
| `nist_800_171` | NIST SP 800-171 Rev 3 | compliance | 97 | NIST SP 800-171 Rev 3 |
| `ny_dfs` | NY DFS Part 500 | compliance | 44 | NY DFS Cybersecurity Regulation |
| `pci_dss` | PCI-DSS v4.0 | compliance | 12 | PCI DSS v4.0.1 |
| `pqc` | PQC Readiness | compliance | 13 | Post-Quantum Cryptography Readiness |
| `sec_cyber` | SEC Cybersecurity Rules | compliance | 22 | SEC Cybersecurity Disclosure Rules |
| `sentinel_ansible` | Sentinel: Ansible Enforcement | compliance | 5 |  |
| `sentinel_dockerfile` | Sentinel: Dockerfile Enforcement | compliance | 19 |  |
| `sentinel_kubernetes` | Sentinel: Kubernetes Enforcement | compliance | 21 |  |
| `sentinel_terraform` | Sentinel: Terraform Enforcement | compliance | 4 |  |
| `soc2` | SOC 2 Type II | compliance | 28 | SOC 2 - AICPA Trust Services Criteria (TSP section 100, 2017, points of focus revised 2022) |
| `sox` | Sarbanes-Oxley (SOX) ITGC | compliance | 35 |  |
| `swift_csp` | SWIFT Customer Security Programme | compliance | 32 | SWIFT Customer Security Programme (CSP) |
| `tisax` | TISAX | compliance | 51 | TISAX (Trusted Information Security Assessment Exchange) |
| `ai_governance` | AI Governance Framework | ot | 2 |  |
| `ami_device` | AMI Device Compliance | ot | 16 | AMI 2.0 Device Compliance |
| `ami_headend` | AMI Head-End Security | ot | 20 | AMI Head-End Security |
| `ami_nist_ir7628` | AMI / NIST IR 7628 | ot | 37 | NIST IR 7628 Rev 1 |
| `iec_62443` | IEC 62443 (OT/ICS Security) | ot | 100 | IEC 62443 |
| `nerc_cip` | NERC CIP (CIP-002 to CIP-015) | ot | 33 | NERC CIP — Critical Infrastructure Protection |
| `nist_800_82` | NIST SP 800-82 Rev 3 (ICS/OT) | ot | 35 | NIST Special Publication 800-82 Rev 3 |
| `nist_ai_rmf` | NIST AI Risk Management Framework | ot | 72 | NIST AI Risk Management Framework (AI RMF) |
| `cis_aks` | CIS AKS | security | 50 | CIS Azure Kubernetes Service (AKS) Benchmark v2.1.0 |
| `cis_amazon_linux_2023` | CIS Amazon Linux 2023 | security | 179 | CIS Amazon Linux 2023 Benchmark v1.0.0 |
| `cis_aws` | CIS AWS Foundations | security | 94 | CIS Amazon Web Services Foundations Benchmark |
| `cis_azure` | CIS Azure Foundations | security | 128 | CIS Microsoft Azure Foundations Benchmark |
| `cis_cisco_ios_xe_17` | CIS Network Devices | security | 84 | CIS Cisco IOS XE 17.x Benchmark v2.2.2 |
| `cis_debian_11` | CIS Debian 11 | security | 163 | DERIVED from CIS Ubuntu Linux 20.04 LTS Benchmark v3.0.0 — applied to Debian 11 (provenance: see README) |
| `cis_docker` | CIS Docker | security | 117 | CIS Docker Benchmark v1.9.0 |
| `cis_eks` | CIS EKS | security | 47 | CIS Amazon EKS Benchmark |
| `cis_gcp` | CIS GCP Foundations | security | 93 | CIS Google Cloud Platform Foundation Benchmark |
| `cis_gke` | CIS GKE | security | 40 | CIS Google GKE Benchmark |
| `cis_kubernetes` | CIS Kubernetes | security | 134 | CIS Kubernetes Benchmark v2.1.0 |
| `cis_m365_v7` | CIS SaaS / M365 | security | 160 | CIS Microsoft 365 Foundations Benchmark |
| `cis_oci` | CIS Oracle Cloud Infrastructure Foundations | security | 54 | CIS Oracle Cloud Infrastructure Foundations Benchmark v3.1 |
| `cis_openshift` | CIS OpenShift | security | 115 | CIS Red Hat OpenShift Container Platform Benchmark v2.0.0 |
| `cis_opnsense` | CIS Network Devices | security | 29 | CIS OPNsense Benchmark v1.0.0 |
| `cis_palo_alto_panos` | CIS Network Devices | security | 79 | CIS Palo Alto Firewall 11 Benchmark v1.2.1 |
| `cis_pfsense` | CIS pfSense | security | 33 | CIS pfSense Firewall Benchmark v1.1.1 |
| `cis_postgresql` | CIS PostgreSQL | security | 72 | CIS PostgreSQL 17 Benchmark v1.1.0 |
| `cis_rhel10` | CIS RHEL 10 | security | 312 | CIS Red Hat Enterprise Linux 10 Benchmark v1.0.1 |
| `cis_rhel8` | CIS RHEL 8 | security | 257 | CIS Red Hat Enterprise Linux 8 Benchmark v4.0.0 |
| `cis_rhel9` | CIS RHEL 9 | security | 263 | CIS Red Hat Enterprise Linux 9 Benchmark v3.0.0 |
| `cis_rocky_linux_8` | CIS Rocky Linux 8 | security | 257 | CIS Rocky Linux 8 Benchmark v3.0.0 |
| `cis_rocky_linux_9` | CIS Rocky Linux 9 | security | 263 | CIS Rocky Linux 9 Benchmark v3.0.0 |
| `cis_ubuntu_2004` | CIS Ubuntu 20.04 | security | 163 | CIS Ubuntu Linux 20.04 LTS Benchmark v3.0.0 |
| `cis_ubuntu_2204` | CIS Ubuntu 22.04 | security | 246 | CIS Ubuntu Linux 22.04 LTS Benchmark v3.0.0 |
| `cis_ubuntu_2404` | CIS Ubuntu 24.04 | security | 258 | CIS Ubuntu Linux 24.04 LTS Benchmark v2.0.1 |
| `cis_vmware_esxi` | CIS VMware | security | 134 | CIS VMware ESXi 8.0 Benchmark v1.4.0 |
| `cis_vmware_esxi_9` | CIS VMware | security | 134 | CIS VMware ESXi 9.0 Benchmark v1.0.0 |
| `cis_vyos` | CIS VyOS | security | 20 | CIS VyOS Benchmark v1.0.1 |
| `cis_windows_10` | CIS Windows 10 | security | 439 | CIS Microsoft Windows 10 Enterprise Benchmark v5.0.0 |
| `cis_windows_11` | CIS Windows 11 | security | 490 | CIS Microsoft Windows 11 Enterprise Benchmark v5.1.0 |
| `cis_windows_2019` | CIS Windows Server 2019 | security | 393 | CIS Microsoft Windows Server 2019 Benchmark v5.0.0 |
| `cis_windows_2022` | CIS Windows Server 2022 | security | 400 | CIS Microsoft Windows Server 2022 Benchmark v5.1.0 |
| `cis_windows_server_2016` | CIS Windows Server 2016 | security | 415 | CIS Microsoft Windows Server 2016 Benchmark v4.0.0 |
| `crypto_miner_detection` | Crypto Miner Detection | security | 8 |  |
| `k8s_pss` | Kubernetes Pod Security Standards | security | 18 | Kubernetes Pod Security Standards |
| `nist_800_53` | NIST SP 800-53 Rev 5 | security | 266 | NIST SP 800-53 Rev 5 |
| `nist_csf` | NIST Cybersecurity Framework 2.0 | security | 106 | NIST Cybersecurity Framework 2.0 |
| `nist_ssdf` | NIST SSDF (SP 800-218 v1.1) | security | 42 | NIST SSDF (SP 800-218 v1.1) |
| `nsa_cisa_k8s` | NSA/CISA Kubernetes Hardening v1.2 | security | 43 | NSA/CISA Kubernetes Hardening Guidance |
| `scuba_m365` | CISA SCuBA M365 | security | 104 | CISA SCuBA Secure Configuration Baselines for Microsoft 365 |
| `stig_amazon_linux_2023` | DISA STIGs | security | 23 |  |
| `stig_apache_2_4` | DISA STIGs | security | 10 |  |
| `stig_cisco_ios_xe_router` | DISA STIGs | security | 10 |  |
| `stig_kubernetes` | DISA STIGs | security | 92 |  |
| `stig_ms_sql_2016` | DISA STIGs | security | 13 |  |
| `stig_openshift_4` | DISA STIGs | security | 14 |  |
| `stig_oracle_database_19c` | DISA STIGs | security | 96 |  |
| `stig_oracle_linux_8` | DISA STIGs | security | 95 |  |
| `stig_oracle_linux_9` | DISA STIGs | security | 114 |  |
| `stig_oracle_mysql_8` | DISA STIGs | security | 100 |  |
| `stig_postgresql_16` | DISA STIGs | security | 13 |  |
| `stig_rhel8` | DISA STIGs | security | 53 |  |
| `stig_rhel9` | DISA STIGs | security | 104 |  |
| `stig_rke2` | DISA STIGs | security | 21 |  |
| `stig_sles_15` | DISA STIGs | security | 27 |  |
| `stig_ubuntu_2204` | DISA STIGs | security | 22 |  |
| `stig_vsphere_8_esxi` | DISA STIGs | security | 10 |  |
| `stig_windows_11` | DISA STIGs | security | 117 |  |
| `stig_windows_server_2022` | DISA STIGs | security | 103 |  |
| `stig_windows_server_2025` | DISA STIGs | security | 94 |  |

## Keys whose report has no control count

An assessment for these returns a report, but the report does not say how many controls it evaluated, so a percentage cannot be checked against a total. Each is on the `no_control_count` list in `ansible/vars/framework_coverage_known_gaps.yml`.

| Key | Catalog entry | Policy directory |
|---|---|---|
| `cis_controls_v8` | CIS Controls v8.1 | `frameworks/management/cis_controls_v8` |
| `cjis` | FBI CJIS Security Policy | `frameworks/federal/cjis` |
| `cyber_essentials` | UK Cyber Essentials | `frameworks/regional/cyber_essentials` |
| `essential_eight` | ACSC Essential Eight | `frameworks/regional/essential_eight` |
| `irs_1075` | IRS Publication 1075 (FTI) | `frameworks/federal/irs_1075` |
| `zero_trust` | Zero Trust (CISA ZTMM v2.0) | `frameworks/federal/zero_trust` |

## Bundles with no assessable key

These catalog entries can be loaded into OPA but list no key (`opa_keys: []`): an umbrella or legacy directory, a gate policy, or a benchmark assessed by its own playbook under another package. They are not counted above.

| Loader key | Catalog entry | Policy directory |
|---|---|---|
| `cis_windows_server_2022` | CIS Windows Server 2022 (legacy) | `benchmarks/cis/windows_server_2022` |
| `cis_containers` | CIS Containers | `benchmarks/cis/containers` |
| `cis_cloud` | CIS Cloud (multi) | `benchmarks/cis/cloud` |
| `cis_network` | CIS Network (Cisco) | `benchmarks/cis/network` |
| `cis_mobile_devices` | CIS Mobile Devices | `benchmarks/cis/mobile_devices` |
| `cis_databases` | CIS Databases | `benchmarks/cis/databases` |
| `cis_mysql` | CIS MySQL | `benchmarks/cis/mysql` |
| `cis_oracle` | CIS Oracle Database | `benchmarks/cis/oracle` |
| `cis_web_servers` | CIS Web Servers | `benchmarks/cis/web_servers` |
| `cis_apache` | CIS Apache HTTP | `benchmarks/cis/apache` |
| `cis_nginx` | CIS NGINX | `benchmarks/cis/nginx` |
| `cis_os_legacy` | CIS OS (legacy variants) | `benchmarks/cis/os` |
| `nist_rmf` | NIST Risk Management Framework | `frameworks/federal/nist/risk_management_framework` |
| `corporate` | Corporate IT Policy | `frameworks/management/corporate` |
| `technical_debt` | Technical Debt Assessment | `frameworks/management/technical_debt` |
| `git_security` | Git Repository Security | `enforcement/git` |
| `mcp_governance` | MCP Tool Governance | `governance/mcp` |
