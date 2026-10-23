> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab on OpenShift Services, AAP 2.7). Findings to check: HOST:8181x1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

# Ansible Role: gather_filesystem_config

**Authors:** Tim Coulter & Claude
**Date:** October 15, 2025

Gathers comprehensive filesystem configuration for CIS RHEL 9 compliance validation.

## Description

This role performs extensive filesystem security analysis including:
- Disabled uncommon filesystem kernel modules (cramfs, freevxfs, jffs2, hfs, hfsplus, udf)
- Separate partition verification (/tmp, /var, /var/tmp, /var/log, /var/log/audit, /home)
- Mount option validation (nodev, nosuid, noexec)
- Sticky bit verification on world-writable directories
- USB storage module status
- Removable media detection
- Disk usage analysis
- /etc/fstab parsing

## Requirements

- RHEL 9 or compatible system
- Ansible 2.9 or higher
- Root or sudo privileges

## Role Variables

Available variables with defaults (see `defaults/main.yml`):

```yaml
# Required separate partitions per CIS
required_separate_partitions:
  - /tmp
  - /var
  - /var/tmp
  - /var/log
  - /var/log/audit
  - /home

# Required mount options per partition
required_mount_options:
  /tmp: [nodev, nosuid, noexec]
  /dev/shm: [nodev, nosuid, noexec]
  /home: [nodev, nosuid]
  /var: [nodev, nosuid]
  /var/tmp: [nodev, nosuid, noexec]
  /var/log: [nodev, nosuid, noexec]
  /var/log/audit: [nodev, nosuid, noexec]

# Filesystem kernel modules that should be disabled
disabled_filesystems:
  - cramfs
  - freevxfs
  - jffs2
  - hfs
  - hfsplus
  - udf
  - vfat  # Optional, may be needed for EFI

# USB storage control
usb_storage_disabled: false
```

## Dependencies

None.

## Example Playbook

```yaml
---
- name: Gather filesystem configuration
  hosts: rhel9_servers
  become: yes
  roles:
    - gather_filesystem_config

- name: Display filesystem issues
  hosts: rhel9_servers
  tasks:
    - name: Show partitions without required mount options
      debug:
        var: item
      loop: "{{ host_filesystem_facts.separate_partitions.analysis }}"
      when: not item.compliant

    - name: Show filesystems not disabled
      debug:
        var: item
      loop: "{{ host_filesystem_facts.disabled_filesystem_modules.modules }}"
      when: not item.compliant

    - name: Show world-writable directories without sticky bit
      debug:
        var: host_filesystem_facts.sticky_bit.world_writable_without_sticky
      when: host_filesystem_facts.sticky_bit.world_writable_without_sticky | length > 0
```

## Facts Generated

This role sets the following fact variable: `host_filesystem_facts`

### Structure:

```yaml
host_filesystem_facts:
  disabled_filesystem_modules:
    modules:
      - module: cramfs
        loaded: false
        disabled: true
        compliant: true
      - module: freevxfs
        loaded: false
        disabled: true
        compliant: true
    all_compliant: true

  separate_partitions:
    required: [/tmp, /var, /var/tmp, /var/log, /var/log/audit, /home]
    analysis:
      - mount_point: /tmp
        is_separate_partition: true
        device: /dev/mapper/rhel-tmp
        fstype: xfs
        options: [rw, nodev, nosuid, noexec, relatime]
        required_options: [nodev, nosuid, noexec]
        missing_options: []
        has_all_required_options: true
        compliant: true
      - mount_point: /var
        is_separate_partition: false
        compliant: false  # Not a separate partition
    all_present: false
    all_compliant: false

  mount_options:
    tmp:
      exists: true
      is_separate: true
      device: /dev/mapper/rhel-tmp
      fstype: xfs
      options: [rw, nodev, nosuid, noexec, relatime]
      has_nodev: true
      has_nosuid: true
      has_noexec: true
      fully_compliant: true
    dev_shm:
      exists: true
      device: tmpfs
      fstype: tmpfs
      options: [rw, nodev, nosuid, noexec]
      has_nodev: true
      has_nosuid: true
      has_noexec: true
      fully_compliant: true

  sticky_bit:
    required_directories: [/tmp, /var/tmp]
    analysis:
      - directory: /tmp
        exists: true
        mode: "1777"
        has_sticky_bit: true
        world_writable: true
        compliant: true
    world_writable_without_sticky: []  # List of paths
    all_compliant: true

  usb_storage:
    status: disabled
    loaded: false
    disabled: true
    compliant: true

  fstab:
    entries:
      - device: /dev/mapper/rhel-root
        mount_point: /
        fstype: xfs
        options: [defaults]
        dump: "0"
        pass: "0"
    entry_count: 5

  removable_media:
    mounted: []
    count: 0

  disk_usage:
    - mount_point: /
      size: 50G
      used: 10G
      available: 40G
      percent_used: "20%"

  all_mounted_filesystems:
    count: 12
    filesystems: [...]

  compliance_checks:
    all_fs_modules_disabled: true
    all_required_partitions_present: false
    all_mount_options_correct: false
    tmp_partition_secure: true
    dev_shm_secure: true
    sticky_bit_compliant: true
    usb_storage_compliant: true

  collection_timestamp: "2025-10-15T12:34:56Z"
```

## CIS Controls Covered

This role gathers facts for the following CIS RHEL 9 Benchmark controls:

**Section 1.1.1.x - Disable Uncommon Filesystems (9 controls):**
- **1.1.1.1**: Ensure cramfs kernel module is not available
- **1.1.1.2**: Ensure freevxfs kernel module is not available
- **1.1.1.3**: Ensure jffs2 kernel module is not available
- **1.1.1.4**: Ensure hfs kernel module is not available
- **1.1.1.5**: Ensure hfsplus kernel module is not available
- **1.1.1.6**: Ensure udf kernel module is not available
- **1.1.1.7**: Ensure vfat kernel module is not available (if applicable)
- **1.1.1.8**: Ensure usb-storage kernel module is not available
- **1.1.1.9**: Ensure other uncommon filesystem modules disabled

**Section 1.1.2.1.x - /tmp Partition (4 controls):**
- **1.1.2.1.1**: Ensure /tmp is a separate partition
- **1.1.2.1.2**: Ensure nodev option set on /tmp
- **1.1.2.1.3**: Ensure noexec option set on /tmp
- **1.1.2.1.4**: Ensure nosuid option set on /tmp

**Section 1.1.2.2.x - /dev/shm Partition (4 controls):**
- **1.1.2.2.1**: Ensure /dev/shm is a separate partition
- **1.1.2.2.2**: Ensure nodev option set on /dev/shm
- **1.1.2.2.3**: Ensure noexec option set on /dev/shm
- **1.1.2.2.4**: Ensure nosuid option set on /dev/shm

**Section 1.1.2.3.x - /home Partition (3 controls):**
- **1.1.2.3.1**: Ensure /home is a separate partition
- **1.1.2.3.2**: Ensure nodev option set on /home
- **1.1.2.3.3**: Ensure nosuid option set on /home

**Section 1.1.2.4.x - /var Partition (3 controls):**
- **1.1.2.4.1**: Ensure /var is a separate partition
- **1.1.2.4.2**: Ensure nodev option set on /var
- **1.1.2.4.3**: Ensure nosuid option set on /var

**Section 1.1.2.5.x - /var/tmp Partition (4 controls):**
- **1.1.2.5.1**: Ensure /var/tmp is a separate partition
- **1.1.2.5.2**: Ensure nodev option set on /var/tmp
- **1.1.2.5.3**: Ensure noexec option set on /var/tmp
- **1.1.2.5.4**: Ensure nosuid option set on /var/tmp

**Section 1.1.2.6.x - /var/log Partition (4 controls):**
- **1.1.2.6.1**: Ensure /var/log is a separate partition
- **1.1.2.6.2**: Ensure nodev option set on /var/log
- **1.1.2.6.3**: Ensure noexec option set on /var/log
- **1.1.2.6.4**: Ensure nosuid option set on /var/log

**Section 1.1.2.7.x - /var/log/audit Partition (4 controls):**
- **1.1.2.7.1**: Ensure /var/log/audit is a separate partition
- **1.1.2.7.2**: Ensure nodev option set on /var/log/audit
- **1.1.2.7.3**: Ensure noexec option set on /var/log/audit
- **1.1.2.7.4**: Ensure nosuid option set on /var/log/audit

**Section 1.1.x - Additional Controls:**
- **1.1.22**: Ensure sticky bit is set on all world-writable directories

**Total: ~50 controls**

## Usage with OPA

The facts collected by this role can be fed directly into OPA for policy evaluation:

```yaml
- name: Evaluate filesystem compliance with OPA
  uri:
    url: "http://localhost:8181/v1/data/cis/rhel9/section_1/filesystem"
    method: POST
    body_format: json
    body:
      input: "{{ host_filesystem_facts }}"
    return_content: yes
  register: opa_filesystem_result
```

## Security Checks Performed

### 1. Disabled Filesystem Kernel Modules

Verifies that uncommon filesystem types are disabled to reduce attack surface:
- **cramfs**: Compressed ROM filesystem (rarely needed)
- **freevxfs**: Veritas filesystem (rarely needed on Linux)
- **jffs2**: Journalling Flash File System (embedded systems)
- **hfs/hfsplus**: Apple filesystems (rarely needed)
- **udf**: Universal Disk Format (optical media)
- **vfat**: FAT filesystem (may be needed for EFI boot)

**Check Method:**
- `lsmod | grep <module>` - Check if loaded
- `modprobe -n -v <module>` - Check if disabled in modprobe config

### 2. Separate Partitions

Validates that critical directories are on separate partitions:
- **/tmp**: Prevents /tmp filling up root filesystem
- **/var**: Prevents logs from filling root
- **/var/tmp**: Additional temp space isolation
- **/var/log**: Log isolation
- **/var/log/audit**: Audit log protection
- **/home**: User data isolation

**Why Important:** Prevents denial of service from one filesystem filling another.

### 3. Mount Options

Validates secure mount options on partitions:

**nodev**: No device files
- Prevents creation of device files that could be exploited

**nosuid**: No SUID/SGID
- Prevents privilege escalation via SUID programs on this filesystem

**noexec**: No execution
- Prevents running programs from this filesystem
- Critical for /tmp, /var/tmp where attackers often stage exploits

### 4. Sticky Bit on World-Writable Directories

Ensures directories like /tmp have sticky bit set:
- With sticky bit (1777): Only file owner can delete their files
- Without sticky bit (0777): Anyone can delete any file (security risk)

### 5. USB Storage

Validates USB storage module status:
- May need to be disabled in high-security environments
- Prevents data exfiltration via USB drives
- Prevents malware introduction via USB

## Common Issues Detected

**Critical Issues:**
- Required partitions not separate (e.g., /var/log not on separate partition)
- Missing noexec on /tmp or /var/tmp
- World-writable directories without sticky bit
- Uncommon filesystem modules loaded

**Warnings:**
- USB storage enabled (may be intentional)
- Removable media mounted
- Disk usage >80% (operational concern)

## Remediation Examples

### Create Separate /tmp Partition

```bash
# Create LVM logical volume
lvcreate -L 2G -n tmp rhel

# Format filesystem
mkfs.xfs /dev/rhel/tmp

# Add to /etc/fstab
echo "/dev/rhel/tmp  /tmp  xfs  defaults,nodev,nosuid,noexec  0 0" >> /etc/fstab

# Mount
systemctl daemon-reload
mount /tmp
```

### Fix Mount Options

```bash
# Edit /etc/fstab and add options
# Before: /dev/mapper/rhel-tmp  /tmp  xfs  defaults  0 0
# After:  /dev/mapper/rhel-tmp  /tmp  xfs  defaults,nodev,nosuid,noexec  0 0

# Remount
mount -o remount /tmp
```

### Disable Filesystem Module

```bash
# Create modprobe config
echo "install cramfs /bin/false" >> /etc/modprobe.d/cramfs.conf
echo "blacklist cramfs" >> /etc/modprobe.d/cramfs.conf

# Unload if currently loaded
rmmod cramfs 2>/dev/null || true
```

### Fix Sticky Bit

```bash
# Add sticky bit to world-writable directory
chmod +t /path/to/directory

# Verify
ls -ld /path/to/directory
# Should show: drwxrwxrwt
```

## Performance Considerations

This role makes several system calls:
- lsmod checks (9 filesystem modules)
- findmnt for all mounted filesystems
- df for disk usage
- lsblk for removable media
- find for world-writable directories (limited to 20 results)

**Typical runtime**: 3-5 seconds per host

## Example Output

```
TASK [Display filesystem configuration summary] ********************************
ok: [server1] => {
    "msg": [
        "==========================================",
        "Filesystem Configuration Facts",
        "==========================================",
        "Disabled FS Modules: 9/9",
        "Required Separate Partitions: 4/6",
        "Partitions with Correct Options: 4/6",
        "",
        "/tmp partition:",
        "  Separate: True",
        "  nodev: True",
        "  nosuid: True",
        "  noexec: True",
        "",
        "/dev/shm:",
        "  nodev: True",
        "  nosuid: True",
        "  noexec: True",
        "",
        "Sticky Bit Compliance: True",
        "USB Storage: disabled",
        "World-writable without sticky: 0 found",
        "",
        "Compliance Summary:",
        "  FS Modules: True",
        "  Partitions: False",
        "  Mount Options: False",
        "  Sticky Bit: True",
        "=========================================="
    ]
}
```

## Integration with Other Roles

This role complements:
- `gather_grub_security` - Boot configuration
- `gather_auditd_facts` - Audit logs on /var/log/audit
- `gather_logging_config` - Logs on /var/log

## License

Apache-2.0
## Author Information

Created by Tim Coulter & Claude for CIS RHEL 9 compliance automation.
