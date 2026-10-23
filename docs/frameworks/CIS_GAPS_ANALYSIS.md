> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: none specific — unreviewed for 293 days.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# CIS Benchmark Gaps Analysis

**Authors:** Tim Coulter & Claude
**Date:** October 15, 2025


## 📊 Current Implementation Status

### ✅ **Implemented CIS Benchmarks (30 policies)**

#### Operating Systems
- **Linux**: RHEL 8, RHEL 9, RHEL 10, Ubuntu 20.04 LTS, CentOS 8 (5 policies)
- **Windows**: Server 2016, Server 2019, Server 2022, Windows 10 Enterprise, Windows 11 Enterprise (5 policies)

#### Cloud Platforms  
- **AWS** Foundation Benchmark (1 policy)
- **Azure** Foundation Benchmark (1 policy)
- **Google Cloud Platform** Foundation Benchmark (1 policy)

#### Container Technologies
- **Docker** Benchmark (1 policy)
- **Kubernetes** Benchmark (1 policy)
- **OpenShift 4.x** Benchmark (1 policy)

#### Database Platforms
- **MySQL 8.0** Benchmark (1 policy)
- **PostgreSQL 14** Benchmark (1 policy)
- **PostgreSQL 15** Benchmark (1 policy)
- **Oracle Database 19c** Benchmark (1 policy)

#### Web Servers & Applications
- **Apache HTTP Server 2.4** Benchmark (1 policy)
- **NGINX 1.20** Benchmark (1 policy)

#### Virtualization Platforms
- **VMware vCenter 8.0** Benchmark (1 policy)
- **VMware ESXi 8.0** Benchmark (1 policy)

#### Network Devices
- **Cisco** IOS (1 policy)
- **Juniper** JunOS (1 policy) 
- **Palo Alto** PAN-OS (1 policy)
- **Fortinet** FortiGate (1 policy)
- **Arista** EOS (1 policy)

## 🔍 **Missing CIS Benchmarks**

### Critical Missing Operating Systems
- **CentOS 7/9** - Widely used in enterprise (CentOS 8 ✅ completed)
- **Debian 10/11/12** - Popular server OS
- **SUSE Linux Enterprise Server (SLES)** - Enterprise critical
- **Amazon Linux 2/2023** - AWS standard
- **Oracle Linux 7/8/9** - Enterprise database systems
- **AlmaLinux 8/9** - RHEL alternative
- **Rocky Linux 8/9** - RHEL alternative

### Missing Windows Platforms
- **Windows Server 2012 R2** - Legacy but still deployed
- **Windows Server Core** - Minimal installations
- ~~**Windows 10 Enterprise** - ✅ completed~~
- ~~**Windows 11 Enterprise** - ✅ completed~~

### Missing Cloud Platforms
- **Oracle Cloud Infrastructure (OCI)** - Enterprise cloud
- **IBM Cloud** - Enterprise environments
- **Alibaba Cloud** - Global cloud provider
- **DigitalOcean** - Developer cloud platform

### Missing Container & DevOps Platforms
- ~~**OpenShift** - ✅ completed~~
- **Amazon EKS** - AWS Kubernetes service
- **Azure AKS** - Azure Kubernetes service
- **Google GKE** - GCP Kubernetes service
- **Rancher** - Kubernetes management platform
- **VMware Tanzu** - Enterprise Kubernetes

### Missing Database Platforms
- ~~**MySQL 8.0** - ✅ completed~~
- ~~**PostgreSQL 14/15** - ✅ completed~~
- ~~**Oracle Database 19c** - ✅ completed~~
- **PostgreSQL 13** - Additional version coverage
- **MongoDB 5.0/6.0** - Document database
- **Microsoft SQL Server 2019/2022** - Enterprise database
- **Redis 6/7** - In-memory database
- **Elasticsearch 7/8** - Search and analytics

### Missing Web Servers & Applications
- ~~**Apache HTTP Server 2.4** - ✅ completed~~
- ~~**NGINX 1.20+** - ✅ completed~~
- **IIS 10** - Windows web server
- **Tomcat 9/10** - Java application server
- **JBoss/WildFly** - Enterprise Java server

### Missing Desktop Software
- **Google Chrome** - Browser security
- **Mozilla Firefox** - Browser security
- **Microsoft Edge** - Browser security
- **Safari** - macOS browser security
- **Microsoft Office 365** - Productivity suite
- **Adobe Acrobat** - PDF security

### Missing Mobile Platforms
- **iOS 16/17** - Mobile device security
- **Android 12/13/14** - Mobile device security
- **Samsung Knox** - Enterprise mobile security
- **BlackBerry UEM** - Mobile device management

### Missing Network Devices
- **F5 BIG-IP** - Load balancer security
- **A10 Networks** - Application delivery
- **Citrix NetScaler** - Application delivery
- **pfSense** - Open source firewall
- **VyOS** - Open source router
- **Mikrotik RouterOS** - Network equipment

### Missing Virtualization Platforms
- ~~**VMware vSphere 8** (vCenter/ESXi) - ✅ completed~~
- **VMware vSphere 7** - Previous version coverage
- **Microsoft Hyper-V** - Windows virtualization
- **Citrix XenServer** - Enterprise virtualization
- **Proxmox VE** - Open source virtualization
- **KVM/QEMU** - Linux virtualization

### Missing Security Tools
- **Splunk Enterprise** - SIEM platform
- **Elastic Stack** - Security analytics
- **CrowdStrike Falcon** - Endpoint protection
- **Carbon Black** - Endpoint security
- **Nessus** - Vulnerability scanner

## 📈 **Priority Implementation Roadmap**

### **Phase 1 (High Priority) - ✅ COMPLETED**
1. ~~**CentOS 8** - ✅ completed~~
2. ~~**Windows 10/11 Enterprise** - ✅ completed~~
3. ~~**MySQL 8.0** - ✅ completed~~
4. ~~**Apache HTTP 2.4** - ✅ completed~~
5. ~~**PostgreSQL 14/15** - ✅ completed~~
6. ~~**Oracle Database 19c** - ✅ completed~~
7. ~~**NGINX 1.20** - ✅ completed~~
8. ~~**OpenShift 4.x** - ✅ completed~~
9. ~~**VMware vSphere 8** (vCenter/ESXi) - ✅ completed~~

### **Phase 2 (Medium Priority) - Current Focus**
1. **CentOS 7/9** - Complete CentOS series
2. **Debian 10/11/12** - Popular server OS
3. **PostgreSQL 13** - Additional version coverage
4. **MongoDB 5.0/6.0** - Document database
5. **Microsoft SQL Server 2019/2022** - Enterprise database

### **Phase 3 (Lower Priority) - Future Roadmap**
1. **SUSE Linux Enterprise Server**
2. **Amazon Linux 2/2023**
3. **VMware vSphere 7** - Previous version coverage
4. **Microsoft Hyper-V** - Windows virtualization
5. **Browser security** (Chrome, Firefox, Edge)

## 🎯 **Impact Analysis**

### **Business Impact of Missing Benchmarks**
- **75%+ of enterprise environments** use platforms not yet covered
- **Database security gaps** represent high-risk attack vectors
- **Cloud platform gaps** limit multi-cloud compliance strategies
- **Browser/desktop gaps** miss endpoint security compliance

### **Implementation Effort Estimates**
- **Operating Systems**: 2-3 days per OS (high complexity)
- **Databases**: 3-4 days per database (complex configurations)
- **Web Servers**: 1-2 days per server (moderate complexity)
- **Desktop Software**: 2-3 days per application (UI-heavy)
- **Cloud Platforms**: 4-5 days per platform (API complexity)

## 🔧 **Resource Requirements for Gap Closure**

### **Team Scaling Needed**
- **2-3 additional security engineers** with platform expertise
- **1 cloud specialist** for multi-cloud implementations
- **1 database specialist** for database-specific benchmarks
- **6-month timeline** for comprehensive coverage

### **Infrastructure Requirements**
- **Test environments** for each new platform
- **Cloud subscriptions** for testing cloud benchmarks
- **Software licenses** for commercial platforms
- **CI/CD expansion** for automated testing

## 📊 **Completion Metrics**

### **Current Coverage**
- **30 of ~150+ available CIS benchmarks** (20% complete)
- **Core platforms covered** (Linux servers, Windows servers/workstations, major clouds)
- **Database platforms covered** (MySQL 8.0, PostgreSQL 14/15, Oracle 19c)
- **Web server platforms covered** (Apache HTTP Server 2.4, NGINX 1.20)
- **Container platforms covered** (Docker, Kubernetes, OpenShift 4.x)
- **Virtualization platforms covered** (VMware vCenter 8.0, ESXi 8.0)
- **Network infrastructure covered** (enterprise network devices)

### **Target Coverage (Full Implementation)**
- **75+ critical CIS benchmarks** (50% of total available)
- **90%+ of enterprise environments** covered
- **Complete compliance framework** for multi-platform organizations

---

**Assessment Date**: October 2025  
**Next Review**: Monthly during implementation phases  
**Owner**: Security Engineering Team  
**Stakeholders**: Platform Engineering, Compliance, Security Operations