> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab, AAP 2.7). Findings to check: RETIRED-HOSTx1, HOST:8181x1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Git Approval Workflow for Code Changes

## Overview

This approval workflow ensures that changes to critical paths in the repository require proper authorization before being committed or merged.

---

## Protected Paths

The following paths require approval for any changes:

- **`policies/`** - OPA Rego compliance policies
- **`opa/`** - OPA configuration and rules
- **`.github/workflows/`** - CI/CD workflows
- **`aap-integration/`** - Ansible Automation Platform integration
- **`ansible/`** - Ansible playbooks and roles

---

## Approval Process

### Method 1: Commit Message Approval (Local Development)

When committing changes to protected paths locally:

```bash
git add policies/cis_rhel9/new_policy.rego

git commit -m "Add new CIS RHEL 9 policy for SSH configuration

This policy validates SSH configuration according to CIS Benchmark 5.2.

Approved-By: john.doe@example.com"
```

**Key Requirements:**
- Include `Approved-By: <approver-email>` in commit message
- Approver must be in the authorized approvers list
- Pre-commit hook will validate approval

### Method 2: Pull Request Approval (GitHub)

1. **Create a branch**:
   ```bash
   git checkout -b feature/update-cis-policy
   git add policies/cis_rhel9/updated_policy.rego
   git commit -m "Update CIS RHEL 9 firewall policy"
   git push origin feature/update-cis-policy
   ```

2. **Open Pull Request** on GitHub

3. **Automated checks run**:
   - Approval check workflow identifies protected paths
   - Comments on PR listing affected paths
   - Blocks merge until approval received

4. **Request review** from authorized approver

5. **Approver reviews and approves**

6. **Merge** once approved and checks pass

---

## Authorized Approvers

Current authorized approvers:
- `john.doe@example.com`
- `security-team@example.com`
- `compliance-admin@example.com`

### Adding New Approvers

Edit `policies/git_approval/approval_policy.rego`:

```rego
authorized_approvers := {
    "john.doe@example.com",
    "security-team@example.com",
    "compliance-admin@example.com",
    "new.approver@example.com",  # Add new approver
}
```

---

## Pre-commit Hook

The pre-commit hook performs these validations:

### 1. Approval Check
- Detects changes to protected paths
- Verifies "Approved-By:" in commit message
- Blocks commit if approval missing

### 2. Policy Syntax Validation
- Validates Rego policy syntax with `opa check`
- Tests policies against OPA server
- Blocks commit if syntax errors found

### 3. YAML Validation
- Validates YAML syntax in changed files
- Uses Python yaml parser
- Blocks commit if invalid YAML

### 4. Sensitive Data Scanning
- Scans for passwords, API keys, tokens
- Excludes Ansible Vault encrypted content
- Blocks commit if sensitive data detected

---

## Bypassing Approval (Emergency)

In emergency situations, admins can bypass approval:

### Temporarily disable pre-commit hook:
```bash
git commit --no-verify -m "Emergency fix for critical issue

Emergency deployment approved verbally by Security Team.
Ticket: SEC-12345"
```

**Important:** Document the bypass reason and obtain post-hoc approval.

---

## GitHub Branch Protection

Configure branch protection on `main`:

1. Go to: Repository Settings → Branches
2. Add rule for `main`
3. Enable:
   - ☑ Require pull request reviews before merging (1 approval)
   - ☑ Require status checks to pass
     - `approval-check`
     - `policy-validation`
   - ☑ Require conversation resolution before merging
   - ☑ Do not allow bypassing the above settings

---

## Testing the Workflow

### Test 1: Commit to Protected Path Without Approval

```bash
echo "test" >> policies/test.rego
git add policies/test.rego
git commit -m "Test change"
```

**Expected**: Commit blocked with message about missing approval

### Test 2: Commit with Approval

```bash
git commit -m "Test change

Approved-By: john.doe@example.com"
```

**Expected**: Commit succeeds

### Test 3: Commit to Non-Protected Path

```bash
echo "test" >> docs/README.md
git add docs/README.md
git commit -m "Update documentation"
```

**Expected**: Commit succeeds without approval

---

## OPA Policy Evaluation

The approval policy can be tested directly:

```bash
# Create test input
cat > test_input.json <<EOF
{
  "commit_message": "Update policy\n\nApproved-By: john.doe@example.com",
  "changed_files": ["policies/cis_rhel9/test.rego"]
}
EOF

# Evaluate policy
opa eval -d policies/git_approval/ -i test_input.json \
  'data.git.approval.decision' --format pretty
```

**Expected output:**
```json
{
  "approved": true,
  "requires_approval": true,
  "affected_protected_paths": ["policies/cis_rhel9/test.rego"],
  "message": "Changes approved"
}
```

---

## Troubleshooting

### Pre-commit hook not running

```bash
# Check if hook is executable
ls -la .git/hooks/pre-commit

# Make executable
chmod +x .git/hooks/pre-commit

# Test manually
.git/hooks/pre-commit
```

### OPA server not accessible

```bash
# Check OPA is running
curl http://AAP_HOST:8181/health

# If not running, start OPA
podman start opa
```

### Approval not recognized

Check commit message format:
- Must contain `Approved-By:` (case-sensitive)
- Email must be in authorized approvers list
- No extra spaces around colon

**Correct:**
```
Approved-By: john.doe@example.com
```

**Incorrect:**
```
Approved by: john.doe@example.com
approved-by: john.doe@example.com
Approved-By : john.doe@example.com
```

---

## Integration with AAP

Changes approved via this workflow can trigger AAP deployments:

1. **Merge to main** triggers GitHub Actions
2. **Webhook to AAP** (configure in `.github/workflows/deploy.yml`)
3. **AAP validates** changes with OPA
4. **Deploys** approved changes to environment

---

## Audit Trail

All approvals are recorded in:

1. **Git commit messages** - Approved-By field
2. **GitHub PR reviews** - Review comments and approvals
3. **GitHub Actions logs** - Approval check results
4. **OPA decision logs** - Policy evaluation results

Query approval history:
```bash
# Find all approved commits
git log --grep="Approved-By:"

# Find commits to protected paths
git log --all -- policies/
```

---

## Best Practices

1. **Always request approval** for protected path changes
2. **Document reason** for changes in commit message
3. **Test policies** before committing
4. **Review OPA output** to ensure policy works as expected
5. **Keep approvers list** current
6. **Monitor approval patterns** for suspicious activity
7. **Regular audits** of approval workflow compliance

---

## Example Workflow

Complete example of making an approved change:

```bash
# 1. Create feature branch
git checkout -b feature/update-ssh-policy

# 2. Make changes
vim policies/cis_rhel9/ssh_configuration.rego

# 3. Test changes
opa test policies/cis_rhel9/

# 4. Commit with approval
git add policies/cis_rhel9/ssh_configuration.rego
git commit -m "Update SSH configuration policy to enforce key-based auth

- Add check for PasswordAuthentication disabled
- Add check for PubkeyAuthentication enabled
- Update tests for new rules

Approved-By: security-team@example.com"

# 5. Push and create PR
git push origin feature/update-ssh-policy

# 6. Open PR on GitHub, wait for review approval

# 7. Merge once approved
```

---

## Questions?

For questions about the approval workflow:
- Security Team: security-team@example.com
- Compliance Team: compliance-admin@example.com
- Repository: https://github.com/ansible-automated-compliance/aac
