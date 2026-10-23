> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: RETIRED-HOSTx1, AAP-2.5/2.6x1, OLD-AAC-VERx1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# AAP MCP Server Capabilities

**Product:** Ansible Automated Compliance (AAC)
**Component:** AAP MCP Server
**Version:** 1.0
**Endpoint:** `http://AAP_HOST:8004/sse`

---

## Overview

The AAP MCP server exposes Ansible Automation Platform through the Model Context Protocol (MCP), giving Claude Code direct read and write access to AAP. Everything the AAP web UI can do is available through MCP tools — with the exception of editing existing resources.

---

## Read / Query Capabilities

| Category | What You Can Do |
|----------|----------------|
| **Jobs** | List jobs, read job details, get stdout, get job events, get host summaries |
| **Job Templates** | List, read, get launch config, list associated credentials/schedules/labels |
| **Workflow Jobs** | List, read, get workflow nodes and their status |
| **Workflow Job Templates** | List, read, get nodes/labels/schedules |
| **Inventories** | List, read, get hosts/groups/sources, get inventory script/tree |
| **Hosts** | List, read, get ansible_facts, get groups, get job history |
| **Groups** | List, read, get children groups and member hosts |
| **Projects** | List, read, get available playbooks, get schedules |
| **Credentials** | List, read, get owners and input sources |
| **Execution Environments** | List, read, get associated job templates |
| **Schedules** | List, read, get jobs run from a schedule |
| **Organizations / Teams / Users** | List, read, get role assignments and permissions |
| **Instances / Instance Groups** | List, read, get health status and capacity |
| **Roles / RBAC** | List role definitions, read user and team assignments |
| **Activity Stream** | Full audit trail of all AAP actions |
| **Dashboard / Metrics** | Job graphs, metrics endpoint |
| **Notifications** | List notification templates and notification history |
| **Config / Settings** | Read AAP system settings by category |
| **Feature Flags** | Read current feature flag state |

---

## Write / Execute Capabilities

| Category | What You Can Do |
|----------|----------------|
| **Launch Jobs** | Launch any job template (with extra vars and survey answers), relaunch, cancel, create schedules from jobs |
| **Launch Workflows** | Launch workflow job templates, relaunch, approve or deny workflow approval nodes |
| **Ad-hoc Commands** | Run ad-hoc Ansible modules on inventory hosts, cancel, relaunch |
| **Sync Operations** | Trigger project sync (git pull), trigger inventory source sync |
| **Create Job Templates** | Create templates, add credentials, add labels/instance groups, set survey spec |
| **Create Workflow Templates** | Create workflow templates, add nodes, link nodes (success/failure/always), copy workflows |
| **Create Inventories & Hosts** | Create inventories, add hosts and groups, bulk-create or bulk-delete hosts |
| **Create Projects** | Create SCM-backed projects (GitHub, GitLab, etc.) |
| **Create Credentials** | Create credentials of any type (SSH, vault, AWS, etc.), create custom credential types |
| **Create Schedules** | Create recurring schedules for templates, workflows, projects, and inventory sources |
| **Manage Orgs / Teams / Users** | Create organizations, teams, and users; assign roles; add users to teams |
| **Create Instance Groups** | Create instance groups, add execution nodes |
| **Create Notifications** | Create notification templates (email, Slack, webhook, PagerDuty), send test notifications |
| **Bulk Operations** | Bulk-create hosts, bulk-delete hosts, bulk-launch multiple jobs simultaneously |
| **RBAC Assignments** | Create user role assignments, create team role assignments |

---

## What Is NOT Available

| Limitation | Workaround |
|-----------|-----------|
| Cannot edit existing resources (no update/patch) | Delete and recreate, or use the AAP UI |
| No direct SSH / shell access to managed hosts | Use ad-hoc commands via MCP |
| No direct PostgreSQL queries | Use AAC playbooks that query the database |
| No file system access on the AAP controller | Use AAP job templates to write files |
| Cannot delete most resources | Use the AAP UI or API directly |

---

## Common MCP Workflows

### Run a Compliance Assessment
1. Launch job template — get job ID
2. Poll job status until `successful` or `failed`
3. Retrieve stdout for full playbook output

### Create a New Job Template and Launch It
1. Create job template (playbook, inventory, execution environment)
2. Attach credentials
3. Set survey spec if needed
4. Launch template — get job ID

### Sync Project and Launch
1. Trigger project update (git pull)
2. Poll project update status until complete
3. Launch dependent job templates

### Bulk Host Onboarding
1. Create inventory
2. Bulk-create hosts with variables
3. Create groups and assign hosts
4. Launch job template against new inventory

---

## Authentication

All MCP tool calls are authenticated via a Bearer token passed in the MCP server's SSE connection header. The token maps to an AAP application token scoped to the `admin` user with `write` scope.

The current token is stored in `~/.claude.json` under the project's `mcpServers.aap.headers.Authorization` field.

---

*Generated: 2026-03-18 | AAC v2.3.1 | AAP 2.6*
