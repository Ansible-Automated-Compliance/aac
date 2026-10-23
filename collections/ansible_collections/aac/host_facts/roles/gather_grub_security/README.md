> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab on OpenShift Services, AAP 2.7). Findings to check: HOST:8181x1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Ansible Role: gather_grub_security

Gathers comprehensive GRUB bootloader security configuration for CIS RHEL 9 compliance validation.

## Description

This role performs extensive GRUB bootloader security analysis including:
- Boot firmware type detection (UEFI vs BIOS)
- Bootloader password protection verification
- GRUB configuration file permissions validation
- Single-user mode authentication requirements
- Secure boot status (UEFI systems)
- Kernel command-line security parameters
- GRUB timeout and recovery mode settings
- Root password status for single-user access

## Requirements

- RHEL 9 or compatible system
- Ansible 2.9 or higher
- Root or sudo privileges
- GRUB2 bootloader (standard on RHEL 9)

## Role Variables

Available variables with defaults (see `defaults/main.yml`):

```yaml
# GRUB configuration file locations
grub_config_file: "/boot/grub2/grub.cfg"
grub_user_config: "/boot/grub2/user.cfg"
grub_defaults_file: "/etc/default/grub"
uefi_grub_config: "/boot/efi/EFI/redhat/grub.cfg"

# Expected permissions
expected_grub_owner: "root"
expected_grub_group: "root"
expected_grub_mode: "0600"
expected_grub_defaults_mode: "0644"

# Single-user mode services
rescue_service: "rescue.service"
emergency_service: "emergency.service"
```

## Dependencies

None.

## Example Playbook

```yaml
---
- name: Gather GRUB security configuration
  hosts: rhel9_servers
  become: yes
  roles:
    - gather_grub_security

- name: Display bootloader security issues
  hosts: rhel9_servers
  tasks:
    - name: Show bootloader password status
      debug:
        msg: "Bootloader password is {{ 'SET' if host_grub_facts.bootloader_password.is_set else 'NOT SET' }}"

    - name: Show insecure configuration files
      debug:
        msg: "GRUB configuration files are not properly secured!"
      when: not host_grub_facts.compliance_checks.all_configs_secure

    - name: Show single-user mode authentication issues
      debug:
        msg: "Single-user mode does not require authentication!"
      when: not host_grub_facts.single_user_mode.authentication_required
```

## Facts Generated

This role sets the following fact variable: `host_grub_facts`

### Structure:

```yaml
host_grub_facts:
  boot_firmware:
    type: "UEFI"                    # or "BIOS"
    is_uefi: true
    grub_config_path: "/boot/efi/EFI/redhat/grub.cfg"
    secure_boot_status: "SecureBoot enabled"

  bootloader_password:
    is_set: true                    # CIS 1.4.1
    user_cfg_exists: true
    user_cfg_has_password: true
    main_cfg_has_password: false
    defaults_password_config: "none"

  config_file_permissions:          # CIS 1.4.2
    grub_cfg:
      path: "/boot/efi/EFI/redhat/grub.cfg"
      exists: true
      owner: "root"
      group: "root"
      mode: "0600"
      is_secure: true
    user_cfg:
      path: "/boot/grub2/user.cfg"
      exists: true
      owner: "root"
      group: "root"
      mode: "0600"
      is_secure: true
    defaults:
      path: "/etc/default/grub"
      exists: true
      owner: "root"
      group: "root"
      mode: "0644"
      is_secure: true

  single_user_mode:                 # CIS 1.4.3
    authentication_required: true
    rescue_service:
      requires_auth: true
      exec_start: "ExecStart=-/usr/lib/systemd/systemd-sulogin-shell rescue"
    emergency_service:
      requires_auth: true
      exec_start: "ExecStart=-/usr/lib/systemd/systemd-sulogin-shell emergency"
    root_password_set: true
    root_password_status: "PS"      # Password Set

  grub_configuration:
    timeout: "5"
    disable_recovery: "true"
    kernel_parameters: "rhgb quiet audit=1"
    audit_enabled: true
    audit_backlog_limit: "8192"
    menu_entries:
      - "Red Hat Enterprise Linux (5.14.0-284.el9.x86_64) 9.2 (Plow)"
      - "Red Hat Enterprise Linux (0-rescue-xxx) 9.2 (Plow)"

  compliance_checks:
    bootloader_password_set: true
    grub_cfg_secure: true
    user_cfg_secure: true
    defaults_secure: true
    all_configs_secure: true
    single_user_auth_required: true

  collection_timestamp: "2025-10-15T12:34:56Z"
```

## CIS Controls Covered

This role gathers facts for the following CIS RHEL 9 Benchmark controls:

**Section 1.4.x - Bootloader Security:**
- **1.4.1**: Ensure bootloader password is set
- **1.4.2**: Ensure bootloader config files are configured
- **1.4.3**: Ensure authentication required for single user mode

**Total: 3 controls**

## Usage with OPA

The facts collected by this role can be fed directly into OPA for policy evaluation:

```yaml
- name: Evaluate GRUB security compliance with OPA
  uri:
    url: "http://localhost:8181/v1/data/cis/rhel9/section_1/bootloader"
    method: POST
    body_format: json
    body:
      input: "{{ host_grub_facts }}"
    return_content: yes
  register: opa_grub_result
```

## Security Checks Performed

### 1. Bootloader Password Protection (CIS 1.4.1)

Verifies that GRUB bootloader requires authentication to modify boot parameters:

- Checks `/boot/grub2/user.cfg` for password_pbkdf2 entries
- Validates main grub.cfg for password configuration
- Examines /etc/default/grub for password-related settings
- **Security Impact**: Prevents unauthorized kernel parameter modification

**Best Practice**: Always set a strong bootloader password using:
```bash
grub2-setpassword
```

### 2. Configuration File Permissions (CIS 1.4.2)

Validates proper ownership and permissions on GRUB configuration files:

- **grub.cfg**: Should be root:root 0600 (read/write by root only)
- **user.cfg**: Should be root:root 0600 (contains password hash)
- **/etc/default/grub**: Should be root:root 0644 (read by all, write by root)

**Security Impact**: Prevents unauthorized viewing or modification of boot configuration

### 3. Single-User Mode Authentication (CIS 1.4.3)

Ensures password is required when booting into single-user/rescue mode:

- Validates rescue.service uses `sulogin` for authentication
- Validates emergency.service uses `sulogin` for authentication
- Confirms root password is set (required for sulogin)
- **Security Impact**: Prevents physical access bypass to root shell

**Rescue/Emergency Services**: Both should have ExecStart lines containing `systemd-sulogin-shell`

## Boot Firmware Types

### UEFI Systems
- GRUB config located at: `/boot/efi/EFI/redhat/grub.cfg`
- Role checks Secure Boot status using `mokutil --sb-state`
- Secure Boot provides additional boot integrity verification

### BIOS/Legacy Systems
- GRUB config located at: `/boot/grub2/grub.cfg`
- Secure Boot not available
- Traditional MBR boot process

The role automatically detects firmware type by checking `/sys/firmware/efi`

## Common Issues Detected

**Critical Issues:**
- No bootloader password set (allows boot parameter tampering)
- GRUB config files world-readable or writable by non-root
- Single-user mode accessible without password
- Root password not set (prevents sulogin from working)

**Warnings:**
- user.cfg doesn't exist but password in main config (less secure)
- GRUB timeout set too high (delays boot)
- Recovery mode enabled (potential security risk)
- Secure Boot disabled on UEFI systems

## Compliance Validation

The role provides a `compliance_checks` section with boolean flags:

```yaml
compliance_checks:
  bootloader_password_set: true/false          # CIS 1.4.1
  all_configs_secure: true/false               # CIS 1.4.2
  single_user_auth_required: true/false        # CIS 1.4.3
```

These can be used directly in assertions or OPA policies.

## Root Password Status Codes

The `root_password_status` field uses `passwd -S` status codes:

- **PS** / **P**: Password set and valid ✓
- **LK** / **L**: Account locked
- **NP**: No password set (CRITICAL ISSUE)
- **unknown**: Unable to determine status

## Additional Security Parameters

The role also collects security-relevant kernel parameters:

### Audit Configuration
- `audit=1`: Enables kernel auditing at boot
- `audit_backlog_limit=N`: Sets audit queue size

### Other Security Parameters
- `rhgb quiet`: Reduces boot verbosity (hides detailed messages)
- `rd.shell=0`: Disables dracut emergency shell
- `systemd.confirm_spawn=0`: Disables service spawn confirmation

## Performance Considerations

This role makes several filesystem and systemd operations:

- File stat operations (4-5 files)
- Content reading (2-3 files)
- systemd service inspection (2 services)
- Shell commands (6-8 total)

**Typical runtime**: 2-3 seconds per host

## Example Output

```
TASK [Display GRUB security facts summary] ************************************
ok: [server1] => {
    "msg": [
        "==========================================",
        "GRUB Bootloader Security Facts",
        "==========================================",
        "Boot Firmware: UEFI",
        "GRUB Config: /boot/efi/EFI/redhat/grub.cfg",
        "",
        "CIS 1.4.1 - Bootloader Password:",
        "  Password Set: True",
        "  user.cfg exists: True",
        "",
        "CIS 1.4.2 - Configuration File Permissions:",
        "  grub.cfg secure: True",
        "  grub.cfg: root:root 0600",
        "  user.cfg secure: True",
        "  defaults secure: True",
        "",
        "CIS 1.4.3 - Single-User Mode Authentication:",
        "  Authentication Required: True",
        "  Rescue Service: True",
        "  Emergency Service: True",
        "  Root Password Set: True",
        "",
        "Compliance Status:",
        "  ✓ Bootloader Password: True",
        "  ✓ Config Files Secure: True",
        "  ✓ Single-User Auth: True",
        "=========================================="
    ]
}
```

## Integration with Other Roles

This role complements:
- `gather_auditd_facts` - GRUB kernel audit parameters should match auditd config
- `gather_user_security` - Root account security (password set)
- `gather_filesystem_config` - Boot partition mounting and permissions

## Remediation Examples

### Set Bootloader Password
```bash
# RHEL 9 recommended method
grub2-setpassword

# This creates /boot/grub2/user.cfg with encrypted password
# Users will need to press 'e' at GRUB menu and enter username/password
```

### Fix Configuration File Permissions
```bash
# Fix grub.cfg permissions
chmod 600 /boot/grub2/grub.cfg
chown root:root /boot/grub2/grub.cfg

# Fix user.cfg permissions (if exists)
chmod 600 /boot/grub2/user.cfg
chown root:root /boot/grub2/user.cfg

# Fix /etc/default/grub
chmod 644 /etc/default/grub
chown root:root /etc/default/grub
```

### Enable Single-User Mode Authentication
```bash
# Verify sulogin is in use (should be default on RHEL 9)
systemctl cat rescue.service | grep ExecStart
systemctl cat emergency.service | grep ExecStart

# Should show: ExecStart=-/usr/lib/systemd/systemd-sulogin-shell rescue

# Ensure root password is set
passwd root
```

## Troubleshooting

### Issue: user.cfg not found but password claims to be set
**Cause**: Password may be embedded directly in grub.cfg (old method)
**Resolution**: Use `grub2-setpassword` to migrate to user.cfg method

### Issue: sulogin not found in rescue/emergency services
**Cause**: Custom systemd unit files or older configuration
**Resolution**: Restore default unit files or create drop-in to use sulogin

### Issue: Role reports UEFI but grub.cfg not in EFI path
**Cause**: Non-standard UEFI configuration or multi-boot setup
**Resolution**: Adjust `uefi_grub_config` variable for custom paths

### Issue: Secure Boot status shows "mokutil not available"
**Cause**: mokutil package not installed (common on minimal installs)
**Resolution**: Install mokutil package: `dnf install mokutil`

## Security Best Practices

1. **Always set bootloader password** - Even on systems with physical security
2. **Restrict GRUB config permissions** - Prevents unauthorized modification
3. **Require single-user authentication** - Critical for physical security
4. **Enable Secure Boot** - Additional layer of boot integrity on UEFI
5. **Disable recovery mode** - Set GRUB_DISABLE_RECOVERY=true unless needed
6. **Set appropriate timeout** - Balance security and usability (5 seconds recommended)

## License

Apache-2.0
## Author Information

Created for CIS RHEL 9 compliance automation.
