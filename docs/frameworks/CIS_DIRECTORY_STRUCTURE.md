> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: none specific — unreviewed for 293 days.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# CIS Benchmark Complete Directory Structure

This document outlines the comprehensive directory structure for all CIS (Center for Internet Security) benchmark technologies and platforms.

## Root Structure

```
policies/
├── cloud_providers/           # Cloud platform benchmarks
├── desktop_software/          # Desktop application benchmarks  
├── devsecops_tools/           # DevSecOps and container benchmarks
├── disa_stig/                 # DISA STIG compliance benchmarks
├── mobile_devices/            # Mobile device benchmarks
├── network_devices/           # Network infrastructure benchmarks
├── operating_systems/         # Operating system benchmarks
└── server_software/           # Server application benchmarks
```

## Detailed Structure by Category

### 1. Cloud Providers (`cloud_providers/`)

```
cloud_providers/
├── aws/
│   ├── 01_identity_access_management/
│   ├── 02_storage/
│   ├── 03_logging/
│   ├── 04_monitoring/
│   ├── 05_networking/
│   └── 06_compute/
├── azure/
│   ├── 01_identity_access_management/
│   ├── 02_security_center/
│   ├── 03_storage_accounts/
│   ├── 04_database_services/
│   ├── 05_logging_monitoring/
│   ├── 06_networking/
│   ├── 07_virtual_machines/
│   ├── 08_key_vault/
│   └── 09_app_service/
├── google_cloud/
├── oracle_cloud/
└── alibaba_cloud/
```

### 2. Desktop Software (`desktop_software/`)

```
desktop_software/
├── microsoft_office/
├── windows_10/
├── windows_11/
└── macos/
```

### 3. DevSecOps Tools (`devsecops_tools/`)

```
devsecops_tools/
├── docker/
│   ├── 01_host_configuration/
│   ├── 02_docker_daemon_configuration/
│   ├── 03_docker_daemon_files/
│   ├── 04_container_images/
│   ├── 05_container_runtime/
│   └── 06_docker_security_operations/
├── kubernetes/
│   ├── 01_master_node_security/
│   ├── 02_etcd/
│   ├── 03_control_plane/
│   ├── 04_worker_nodes/
│   └── 05_policies/
├── jenkins/
├── terraform/
└── ansible/
```

### 4. DISA STIG (`disa_stig/`)

```
disa_stig/
└── [DISA Security Technical Implementation Guides]
```

### 5. Mobile Devices (`mobile_devices/`)

```
mobile_devices/
├── ios/
└── android/
```

### 6. Network Devices (`network_devices/`)

```
network_devices/
├── cisco/
├── juniper/
├── palo_alto/
└── fortinet/
```

### 7. Operating Systems (`operating_systems/`)

```
operating_systems/
├── linux/
│   ├── redhat/
│   │   ├── 01_initial_setup/
│   │   ├── 02_services/
│   │   ├── 03_network_configuration/
│   │   ├── 04_logging_auditing/
│   │   ├── 05_access_authentication/
│   │   └── 06_system_maintenance/
│   ├── ubuntu/
│   │   ├── 01_initial_setup/
│   │   ├── 02_services/
│   │   ├── 03_network_configuration/
│   │   ├── 04_logging_auditing/
│   │   ├── 05_access_authentication/
│   │   └── 06_system_maintenance/
│   ├── centos/
│   ├── debian/
│   ├── suse/
│   └── amazon_linux/
├── windows/
│   ├── server_2019/
│   ├── server_2022/
│   ├── windows_10/
│   └── windows_11/
└── unix/
    ├── solaris/
    └── aix/
```

### 8. Server Software (`server_software/`)

```
server_software/
├── apache/
├── nginx/
├── mysql/
├── postgresql/
├── oracle/
├── mongodb/
├── redis/
└── elasticsearch/
```

## CIS Benchmark Section Standards

### Linux Operating Systems (Sections 1-6)

1. **Initial Setup**
   - 1.1 Filesystem Configuration
   - 1.2 Configure Software Updates
   - 1.3 FileSystem Integrity Check
   - 1.4 Secure Boot Settings
   - 1.5 Additional Processing Hardening
   - 1.6 Mandatory Access Control
   - 1.7 Warning Banners

2. **Services**
   - 2.1 Inetd Services
   - 2.2 Special Purpose Services
   - 2.3 Service Clients

3. **Network Configuration**
   - 3.1 Network Parameter (Host-Only)
   - 3.2 Network Parameter (Host and Router)
   - 3.3 IPv6
   - 3.4 TCP Wrappers
   - 3.5 Uncommon Network Protocols
   - 3.6 Firewall Configuration

4. **Logging and Auditing**
   - 4.1 Configure System Accounting
   - 4.2 Configure Logging

5. **Access, Authentication and Authorization**
   - 5.1 Configure Cron
   - 5.2 SSH Server Configuration
   - 5.3 Configure PAM
   - 5.4 User Accounts and Environment

6. **System Maintenance**
   - 6.1 System File Permissions
   - 6.2 User and Group Settings

### Cloud Providers

#### AWS Foundations
1. Identity and Access Management
2. Storage
3. Logging
4. Monitoring
5. Networking
6. Compute

#### Azure Foundations
1. Identity and Access Management
2. Microsoft Defender for Cloud
3. Storage Accounts
4. Database Services
5. Logging and Monitoring
6. Networking
7. Virtual Machines
8. Key Vault
9. AppService

### Container Technologies

#### Docker
1. Host Configuration
2. Docker Daemon Configuration
3. Docker Daemon Configuration Files
4. Container Images and Build File
5. Container Runtime
6. Docker Security Operations

#### Kubernetes
1. Master Node Security Configuration
2. etcd
3. Control Plane Configuration
4. Worker Nodes
5. Policies

## Usage Patterns

### File Naming Convention
- Use descriptive names matching CIS control sections
- Include section numbers where applicable
- Use snake_case for file names
- Example: `01_filesystem_configuration.rego`

### Package Naming Convention
- Follow hierarchical structure: `cis.{category}.{technology}.{section}`
- Examples:
  - `cis.linux.redhat.filesystem`
  - `cis.aws.iam`
  - `cis.docker.host`

### Directory Organization
- Each technology has numbered sections matching official CIS benchmarks
- Policies are grouped by functional area
- Test files mirror the policy structure
- Example configurations provided for each technology

## Implementation Status

### ✅ Implemented (CIS Benchmarks)
- **Linux Operating Systems**: RHEL 8, RHEL 9, RHEL 10, Ubuntu 20.04 LTS
- **Windows Operating Systems**: Windows Server 2016, Windows Server 2019, Windows Server 2022
- **Cloud Platforms**: AWS, Azure, Google Cloud Platform
- **Container Technologies**: Docker, Kubernetes
- **Network Devices**: Cisco IOS, Juniper JunOS, Palo Alto PAN-OS, Fortinet FortiOS

### 🚧 In Progress
- Complete Linux distributions (CentOS, Debian, SUSE, Amazon Linux)
- Additional cloud platform sections

### 📋 Planned (Not Yet Implemented)
- **Desktop Software CIS Benchmarks**: 
  - Browser security (Chrome, Firefox, Safari, Edge)
  - Microsoft Office applications
  - Windows 10/11 workstation benchmarks
  - macOS workstation benchmarks
- **Mobile Device CIS Benchmarks**: iOS, Android
- **Server Software CIS Benchmarks**: Apache, NGINX, MySQL, PostgreSQL
- **DISA STIG Integration**: Mapping CIS controls to STIG requirements

### 📁 Current Implementation Structure
```
policies/
├── cis_benchmarks/          # ✅ IMPLEMENTED CIS Benchmarks
│   ├── rhel_8/rhel_9/rhel_10/ubuntu_20_04_lts/  # Linux OS
│   ├── windows_server_2016/2019/2022/           # Windows Server
│   ├── aws/azure/gcp/                           # Cloud Platforms
│   ├── docker/kubernetes/                       # Containers
│   └── network_devices/                         # Network Equipment
├── desktop_software/        # 📋 PLACEHOLDER (Not Implemented)
├── mobile_devices/         # 📋 PLACEHOLDER (Not Implemented)  
├── server_software/        # 📋 PLACEHOLDER (Not Implemented)
└── disa_stig/             # 📋 PLACEHOLDER (Not Implemented)
```

## Contributing

When adding new CIS benchmarks:

1. Follow the established directory structure
2. Use consistent package naming
3. Include comprehensive test coverage
4. Document input data requirements
5. Provide example configurations

## References

- [CIS Benchmarks Official Site](https://www.cisecurity.org/cis-benchmarks)
- [CIS Controls](https://www.cisecurity.org/controls)
- [Open Policy Agent](https://www.openpolicyagent.org/)
- [Rego Policy Language](https://www.openpolicyagent.org/docs/latest/policy-language/)