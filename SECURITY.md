# Security Policy

## Supported Versions

AAC 2.6.x receives security updates.

| Version | Supported |
|---------|-----------|
| 2.6.x | ✅ Active |
| 2.5.x | ❌ End of life |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

To report a vulnerability:

1. Open a [GitHub Security Advisory](https://github.com/ansible-automated-compliance/aac/security/advisories/new) — this is private by default
2. Include:
   - Description of the vulnerability and its impact
   - Steps to reproduce
   - Affected component (Rego policy, Ansible playbook, script, etc.)
   - Any suggested mitigations

You will receive an acknowledgment within 48 hours and a resolution timeline within 7 days.

## Scope

This repo contains:
- **Rego policies** — assessment logic; a bug here means incorrect compliance scores, not a security exploit. Report these as regular issues.
- **Ansible playbooks** — run with AAP credentials against managed infrastructure. Vulnerabilities here (e.g., command injection, credential exposure) are in scope.
- **Scripts** — utility scripts; credential handling bugs are in scope.

## Credentials in This Repo

- `ansible/vars/vault_secrets.yml` is **gitignored** — never committed
- `ansible/vars/vault_secrets.yml.example` uses only placeholder values
- `ansible/vars/site_config.yml` is **gitignored** — never committed
- The CLAUDE.md file contains non-production default credentials for an isolated Red Hat demo lab. These credentials must not be reused in any environment reachable from a network. Demo environments should always be isolated and rotated before any non-lab use.
