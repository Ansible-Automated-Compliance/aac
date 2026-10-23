# Private Automation Hub Integration for OPA Compliance Libraries

**Authors:** Tim Coulter & Claude
**Date:** October 15, 2025


## Overview
This document outlines the integration strategy for using Red Hat Private Automation Hub as the central repository for OPA compliance libraries, enabling automated distribution and updates across enterprise infrastructure.

## Architecture Components

### 1. Private Automation Hub Structure
```
enterprise-compliance-hub/
├── collections/
│   ├── compliance.pci_dss/
│   │   ├── policies/
│   │   │   ├── requirement_1.rego
│   │   │   ├── requirement_3.rego
│   │   │   └── ...
│   │   ├── tests/
│   │   ├── meta/
│   │   └── galaxy.yml
│   ├── compliance.sox/
│   │   ├── policies/
│   │   │   ├── sox_simplified.rego
│   │   │   └── ...
│   │   ├── tests/
│   │   └── galaxy.yml
│   ├── compliance.cis/
│   ├── compliance.nist/
│   └── compliance.iso27001/
├── execution-environments/
│   ├── opa-compliance-ee/
│   │   ├── Containerfile
│   │   ├── requirements.yml
│   │   └── execution-environment.yml
│   └── compliance-reporter-ee/
└── automation-content/
    ├── playbooks/
    ├── roles/
    └── workflows/
```

### 2. Collection Metadata Structure

#### PCI DSS Collection (galaxy.yml)
```yaml
namespace: compliance
name: pci_dss
version: 1.0.0
readme: README.md
authors:
  - Enterprise Compliance Team
description: PCI DSS v4.0 compliance policies for OPA
license:
  - Apache-2.0
tags:
  - compliance
  - pci_dss
  - opa
  - security
dependencies:
  compliance.common: ">=1.0.0"
repository: https://github.com/enterprise/compliance-pci-dss
documentation: https://docs.enterprise.com/compliance/pci-dss
homepage: https://compliance.enterprise.com
issues: https://github.com/enterprise/compliance-pci-dss/issues
```

#### SOX Collection (galaxy.yml)
```yaml
namespace: compliance
name: sox
version: 1.0.0
readme: README.md
authors:
  - Enterprise Compliance Team
description: Sarbanes-Oxley Act compliance policies for OPA
license:
  - Apache-2.0
tags:
  - compliance
  - sox
  - financial
  - opa
dependencies:
  compliance.common: ">=1.0.0"
repository: https://github.com/enterprise/compliance-sox
```

### 3. Ansible Automation Platform for OPA Library Distribution

#### OPA Policy Deployment Playbook
```yaml
---
- name: Deploy OPA Compliance Policies
  hosts: opa_agents
  gather_facts: yes
  vars:
    compliance_frameworks:
      - pci_dss
      - sox
      - cis
    opa_policy_dir: /etc/opa/policies
    backup_dir: /etc/opa/policies/backup
    
  tasks:
    - name: Create backup of existing policies
      archive:
        path: "{{ opa_policy_dir }}"
        dest: "{{ backup_dir }}/policies-{{ ansible_date_time.epoch }}.tar.gz"
        format: gz
      when: opa_policy_dir is exists

    - name: Install compliance collections from Private Automation Hub
      ansible.builtin.command:
        cmd: ansible-galaxy collection install compliance.{{ item }} --force
      loop: "{{ compliance_frameworks }}"
      delegate_to: localhost
      run_once: true

    - name: Deploy PCI DSS policies
      copy:
        src: "{{ ansible_collections_path }}/compliance/pci_dss/policies/"
        dest: "{{ opa_policy_dir }}/pci_dss/"
        owner: opa
        group: opa
        mode: '0644'
      notify: reload_opa

    - name: Deploy SOX policies
      copy:
        src: "{{ ansible_collections_path }}/compliance/sox/policies/"
        dest: "{{ opa_policy_dir }}/sox/"
        owner: opa
        group: opa
        mode: '0644'
      notify: reload_opa

    - name: Validate OPA policies
      shell: opa fmt --diff {{ opa_policy_dir }}
      register: opa_validation
      failed_when: opa_validation.rc != 0

    - name: Update policy registry in database
      uri:
        url: "{{ compliance_api_endpoint }}/api/v1/policies/register"
        method: POST
        headers:
          Authorization: "Bearer {{ api_token }}"
          Content-Type: "application/json"
        body_format: json
        body:
          node_id: "{{ inventory_hostname }}"
          frameworks: "{{ compliance_frameworks }}"
          policies_updated: "{{ ansible_date_time.iso8601 }}"
          validation_status: "{{ 'passed' if opa_validation.rc == 0 else 'failed' }}"

  handlers:
    - name: reload_opa
      systemd:
        name: opa
        state: reloaded
```

### 4. Automated Update Workflow

#### Compliance Library Update Job Template
```yaml
---
- name: Automated Compliance Library Updates
  hosts: localhost
  gather_facts: no
  vars:
    automation_hub_url: "{{ vault_automation_hub_url }}"
    automation_hub_token: "{{ vault_automation_hub_token }}"
    update_schedule: "daily"
    notification_webhook: "{{ vault_slack_webhook }}"

  tasks:
    - name: Check for collection updates
      uri:
        url: "{{ automation_hub_url }}/api/galaxy/v3/collections/compliance/"
        headers:
          Authorization: "Token {{ automation_hub_token }}"
      register: available_collections

    - name: Compare versions with deployed collections
      set_fact:
        updates_available: "{{ available_collections.json | json_query(version_query) }}"
      vars:
        version_query: "data[?name=='pci_dss' || name=='sox'].{name: name, version: latest_version.version}"

    - name: Trigger update deployment if newer versions available
      ansible.builtin.awx.job_launch:
        job_template: "Deploy OPA Compliance Policies"
        extra_vars:
          force_update: true
          new_versions: "{{ updates_available }}"
      when: updates_available | length > 0

    - name: Send notification of updates
      uri:
        url: "{{ notification_webhook }}"
        method: POST
        body_format: json
        body:
          text: "Compliance libraries updated: {{ updates_available | map(attribute='name') | join(', ') }}"
      when: updates_available | length > 0
```

### 5. Execution Environment for Compliance Operations

#### Containerfile for OPA Compliance EE
```dockerfile
ARG EE_BASE_IMAGE=registry.redhat.io/ubi8/ubi:latest
FROM $EE_BASE_IMAGE

USER root

# Install OPA binary
RUN curl -L -o opa https://openpolicyagent.org/downloads/v1.10.0/opa_linux_amd64_static && \
    chmod +x opa && \
    mv opa /usr/local/bin/

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install -r /tmp/requirements.txt

# Install Ansible collections
COPY requirements.yml /tmp/requirements.yml
RUN ansible-galaxy collection install -r /tmp/requirements.yml

USER 1000
```

#### requirements.yml for Collections
```yaml
---
collections:
  - name: compliance.pci_dss
    source: https://automation-hub.enterprise.com/
    version: ">=1.0.0"
  - name: compliance.sox
    source: https://automation-hub.enterprise.com/
    version: ">=1.0.0"
  - name: compliance.common
    source: https://automation-hub.enterprise.com/
    version: ">=1.0.0"
  - name: kubernetes.core
    version: ">=2.4.0"
  - name: redhat.openshift
    version: ">=2.2.0"
```

### 6. Integration with Database Configuration API

#### Updated API Endpoints for Automation Hub Integration
```python
# Additional endpoints in compliance_api.py

@app.post("/api/v1/automation-hub/sync")
async def sync_automation_hub_collections(
    sync_request: AutomationHubSyncRequest,
    db: Session = Depends(get_db)
):
    """Synchronize available collections from Private Automation Hub"""
    
    # Fetch collections from Automation Hub
    hub_collections = await fetch_hub_collections(sync_request.hub_url, sync_request.token)
    
    # Update database with available collections
    for collection in hub_collections:
        db_collection = ComplianceCollection(
            namespace=collection.namespace,
            name=collection.name,
            version=collection.version,
            description=collection.description,
            source_url=collection.download_url,
            checksum=collection.checksum,
            last_updated=datetime.utcnow()
        )
        db.merge(db_collection)
    
    db.commit()
    return {"status": "success", "collections_synced": len(hub_collections)}

@app.post("/api/v1/deployments/schedule")
async def schedule_policy_deployment(
    deployment: PolicyDeploymentRequest,
    db: Session = Depends(get_db)
):
    """Schedule automated policy deployment across infrastructure"""
    
    # Launch AAP job template via Controller API
    # (replace with your preferred HTTP client; shown here as a conceptual call)
    resp = requests.post(
        f"{deployment.aap_url}/api/controller/v2/job_templates/launch/",
        headers={"Authorization": f"Bearer {deployment.aap_token}"},
        json={
            "template_name": "Deploy OPA Compliance Policies",
            "extra_vars": {
                "target_frameworks": deployment.frameworks,
                "target_environments": deployment.environments,
                "rollback_on_failure": deployment.rollback_enabled,
            },
        },
    )
    resp.raise_for_status()
    job_id = resp.json()["id"]
    
    # Track deployment in database
    db_deployment = PolicyDeployment(
        job_id=job_id,
        frameworks=deployment.frameworks,
        environments=deployment.environments,
        status="running",
        initiated_by=deployment.user_id,
        created_at=datetime.utcnow()
    )
    db.add(db_deployment)
    db.commit()
    
    return {"deployment_id": db_deployment.id, "aap_job_id": job_id}

@app.get("/api/v1/deployments/{deployment_id}/status")
async def get_deployment_status(
    deployment_id: int,
    db: Session = Depends(get_db)
):
    """Get status of policy deployment"""
    
    deployment = db.query(PolicyDeployment).filter(
        PolicyDeployment.id == deployment_id
    ).first()
    
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    # Fetch current status from AAP
    aap_status = await fetch_job_status(deployment.job_id)
    
    # Update database with current status
    deployment.status = aap_status.status
    deployment.updated_at = datetime.utcnow()
    db.commit()
    
    return {
        "deployment_id": deployment_id,
        "status": deployment.status,
        "frameworks": deployment.frameworks,
        "environments": deployment.environments,
        "aap_job_id": deployment.job_id,
        "created_at": deployment.created_at,
        "updated_at": deployment.updated_at
    }
```

### 7. Monitoring and Alerting Integration

#### Policy Update Monitoring Dashboard
```python
# monitoring/automation_hub_monitor.py

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict

class AutomationHubMonitor:
    def __init__(self, hub_url: str, token: str, db_session):
        self.hub_url = hub_url
        self.token = token
        self.db = db_session
        self.logger = logging.getLogger(__name__)

    async def monitor_collection_updates(self):
        """Monitor for new collection versions and trigger updates"""
        
        while True:
            try:
                # Check for updates every hour
                await asyncio.sleep(3600)
                
                current_collections = await self.fetch_current_collections()
                deployed_collections = self.get_deployed_collections()
                
                updates_needed = self.compare_versions(current_collections, deployed_collections)
                
                if updates_needed:
                    await self.trigger_update_workflow(updates_needed)
                    
            except Exception as e:
                self.logger.error(f"Error monitoring collections: {e}")

    def get_deployed_collections(self) -> List[Dict]:
        """Get currently deployed collection versions from database"""
        
        return self.db.query(ComplianceCollection).all()

    async def trigger_update_workflow(self, updates: List[Dict]):
        """Trigger Ansible workflow for policy updates"""
        
        workflow_data = {
            "updates": updates,
            "timestamp": datetime.utcnow().isoformat(),
            "auto_triggered": True
        }
        
        # Launch AAP workflow template
        job_id = await self.launch_workflow_template(
            "Compliance Library Update Workflow",
            workflow_data
        )
        
        self.logger.info(f"Triggered update workflow: {job_id}")
        
        # Send notification
        await self.send_update_notification(updates, job_id)
```

## Deployment Strategy

### Phase 1: Initial Setup
1. Configure Private Automation Hub with compliance collections
2. Create execution environments for OPA operations
3. Develop Ansible Automation Platform playbooks and job templates
4. Set up database integration

### Phase 2: Automated Distribution
1. Deploy OPA agents across infrastructure
2. Implement automated policy distribution
3. Configure monitoring and alerting
4. Test update workflows

### Phase 3: Production Operations
1. Enable scheduled updates
2. Implement rollback procedures
3. Set up compliance reporting
4. Monitor and optimize performance

## Benefits

1. **Centralized Management**: Single source of truth for compliance policies
2. **Version Control**: Proper versioning and change tracking
3. **Automated Distribution**: Consistent policy deployment across infrastructure
4. **Integration**: Seamless integration with existing Ansible Automation Platform
5. **Monitoring**: Real-time visibility into policy deployment status
6. **Scalability**: Efficient distribution to thousands of nodes
7. **Compliance**: Audit trail and evidence collection

## Security Considerations

1. **Access Control**: Role-based access to collections and deployments
2. **Encryption**: TLS encryption for all hub communications
3. **Validation**: Policy validation before deployment
4. **Rollback**: Automated rollback on validation failures
5. **Audit Trail**: Complete deployment and update history