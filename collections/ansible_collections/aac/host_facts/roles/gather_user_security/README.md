> [!WARNING]
> **STALE — flagged by the handover audit (2026-08-31).** Not verified against the current
> architecture (post-CRC lab on OpenShift Services, AAP 2.7). Findings to check: HOST:8181x1.
> Treat specifics as unreliable until reviewed — see
> `docs/reports/HANDOVER_AUDIT_2026-08-31.md`. Remove this banner after review.

## Ansible Role: gather_user_security

Gathers comprehensive user account security facts for CIS RHEL 9 compliance validation.

## Description

This role performs extensive user account security analysis including:
- Complete user and group enumeration from `/etc/passwd`, `/etc/shadow`, `/etc/group`
- User classification (interactive vs system accounts)
- Password aging policy validation
- Home directory existence, ownership, and permissions
- Insecure dotfile detection (.netrc, .forward, .rhosts)
- Shell timeout (TMOUT) configuration
- Default umask validation
- Root PATH integrity checks
- Duplicate UID/GID/username detection
- System account security validation
- Root account verification (UID 0, GID 0)
- Shadow file integrity checks

## Requirements

- RHEL 9 or compatible system
- Ansible 2.9 or higher
- Root or sudo privileges (required to read /etc/shadow)

## Role Variables

Available variables with defaults (see `defaults/main.yml`):

```yaml
# System UID threshold (users below this are system accounts)
system_uid_min: 1000

# Files to check in user home directories
user_dotfiles_to_check:
  - .netrc
  - .forward
  - .rhosts

# Shells that indicate a disabled account
disabled_shells:
  - /sbin/nologin
  - /usr/sbin/nologin
  - /bin/false

# Maximum acceptable umask
max_acceptable_umask: "027"

# Maximum acceptable shell timeout (seconds)
max_acceptable_timeout: 900

# Expected home directory permissions
expected_home_dir_mode: "750"
```

## Dependencies

None.

## Example Playbook

```yaml
---
- name: Gather user security facts
  hosts: rhel9_servers
  become: yes
  roles:
    - gather_user_security

- name: Display user security issues
  hosts: rhel9_servers
  tasks:
    - name: Show duplicate UIDs
      debug:
        var: host_user_security_facts.duplicates.uids
      when: host_user_security_facts.duplicates.has_duplicate_uids

    - name: Show insecure dotfiles
      debug:
        var: host_user_security_facts.dotfiles.violations
      when: host_user_security_facts.dotfiles.has_violations

    - name: Show system account violations
      debug:
        var: host_user_security_facts.system_account_security.violations
      when: host_user_security_facts.system_account_security.has_violations
```

## Facts Generated

This role sets the following fact variable: `host_user_security_facts`

### Structure:

```yaml
host_user_security_facts:
  users:
    all_users: [...]           # All users from /etc/passwd
    interactive_users: [...]   # UID >= 1000, valid shell
    system_accounts: [...]     # UID < 1000, UID != 0
    total_users: 42
    interactive_count: 5
    system_count: 36

  groups:
    all_groups: [...]
    total_groups: 45

  password_aging:
    users_with_aging:
      - name: "user1"
        uid: 1000
        aging_info:
          "Last password change": "Oct 15, 2025"
          "Password expires": "Jan 13, 2026"
          "Password inactive": "never"
          # ... other aging fields

  home_directories:
    info:
      - user: "user1"
        path: "/home/user1"
        exists: true
        owner: "user1"
        group: "user1"
        mode: "0750"
        permissions_octal: "750"
        owned_by_user: true
    missing: [...]              # Homes that don't exist
    wrong_owner: [...]          # Homes not owned by user
    insecure_permissions: [...]  # Homes with mode > 750

  dotfiles:
    violations:
      - user: "user1"
        file: ".netrc"
        path: "/home/user1/.netrc"
    has_violations: true

  shell_security:
    timeout: 900                # TMOUT value in seconds
    timeout_configured: true
    timeout_acceptable: true    # <= max_acceptable_timeout

  umask:
    value: "027"
    acceptable: true            # >= max_acceptable_umask

  root_account:
    uid_zero_accounts:
      - name: "root"
        uid: 0
        gid: 0
    multiple_uid_zero: false
    root_gid: 0
    root_gid_correct: true
    path: "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
    path_directories: [...]
    path_analysis:
      - path: "/usr/local/bin"
        owner: "root"
        permissions: "755"
        world_writable: false
        exists: true
    path_has_dot: false
    path_has_empty: false
    path_world_writable: []

  duplicates:
    uids:
      - uid: 1001
        users: ["user1", "user2"]
    gids: [...]
    usernames: [...]
    has_duplicate_uids: false
    has_duplicate_gids: false
    has_duplicate_usernames: false

  system_account_security:
    violations:
      - user: "daemon"
        uid: 2
        shell: "/bin/bash"
        violations: ["shell_not_disabled"]
    has_violations: false

  shadow_integrity:
    shadow_readable: true
    users_in_passwd: 42
    users_in_shadow: 42
    shadow_passwd_sync: true

  collection_timestamp: "2025-10-15T12:34:56Z"
```

## CIS Controls Covered

This role gathers facts for the following CIS RHEL 9 Benchmark controls:

**Section 5.5.x - User Account Security:**
- **5.5.1.1**: Ensure minimum days between password changes is configured
- **5.5.1.2**: Ensure password expiration is 365 days or less
- **5.5.1.3**: Ensure password expiration warning days is 7 or more
- **5.5.1.4**: Ensure inactive password lock is 30 days or less
- **5.5.1.5**: Ensure all users last password change date is in the past
- **5.5.2**: Ensure system accounts are secured
- **5.5.3**: Ensure default group for the root account is GID 0
- **5.5.4**: Ensure default user umask is 027 or more restrictive
- **5.5.5**: Ensure default user shell timeout is 900 seconds or less

**Section 6.2.x - System Maintenance:**
- **6.2.1**: Ensure accounts in /etc/passwd use shadowed passwords
- **6.2.2**: Ensure /etc/shadow password fields are not empty
- **6.2.3**: Ensure all groups in /etc/passwd exist in /etc/group
- **6.2.5**: Ensure no duplicate UIDs exist
- **6.2.6**: Ensure no duplicate GIDs exist
- **6.2.7**: Ensure no duplicate user names exist
- **6.2.8**: Ensure no duplicate group names exist
- **6.2.9**: Ensure root PATH Integrity
- **6.2.10**: Ensure root is the only UID 0 account
- **6.2.11**: Ensure local interactive user home directories exist
- **6.2.12**: Ensure local interactive users own their home directories
- **6.2.13**: Ensure local interactive user home directories are mode 750 or more restrictive
- **6.2.14**: Ensure no local interactive user has .netrc files
- **6.2.15**: Ensure no local interactive user has .forward files
- **6.2.16**: Ensure no local interactive user has .rhosts files

**Total: 26 controls**

## Usage with OPA

The facts collected by this role can be fed directly into OPA for policy evaluation:

```yaml
- name: Evaluate user security compliance with OPA
  uri:
    url: "http://localhost:8181/v1/data/cis/rhel9/section_5/user_security"
    method: POST
    body_format: json
    body:
      input: "{{ host_user_security_facts }}"
    return_content: yes
  register: opa_user_result
```

## Security Checks Performed

### 1. User Account Validation
- Enumerates all users from `/etc/passwd`
- Classifies users as interactive (UID >= 1000) or system (UID < 1000)
- Validates user shells
- Checks password field in passwd (should be 'x' for shadow passwords)

### 2. Password Aging
- Uses `chage -l` to get detailed password aging for each user
- Checks last password change date
- Validates password expiration settings
- Identifies inactive/expired accounts

### 3. Home Directory Security
- Verifies home directory existence
- Checks ownership (should be owned by user)
- Validates permissions (should be 750 or more restrictive)
- Identifies missing home directories

### 4. Insecure Dotfiles
- Scans for `.netrc` (FTP credentials)
- Scans for `.forward` (email forwarding)
- Scans for `.rhosts` (remote login)
- Reports all instances found

### 5. System Account Security
- Identifies system accounts (UID < 1000, UID != 0)
- Ensures shells are disabled (/sbin/nologin, /bin/false)
- Ensures passwords are locked (!!, *, !)
- Reports violations

### 6. Root Account Integrity
- Finds all UID 0 accounts (should only be 'root')
- Validates root GID is 0
- Analyzes root PATH for:
  - Current directory (.)
  - Empty entries (::)
  - World-writable directories
  - Non-root owned directories

### 7. Duplicate Detection
- Scans for duplicate UIDs across different usernames
- Scans for duplicate GIDs across different group names
- Scans for duplicate usernames with different UIDs

### 8. Shell Security
- Extracts TMOUT value from shell configuration files
- Validates timeout is configured and <= 900 seconds

### 9. Default Umask
- Extracts umask from system configuration
- Validates umask is 027 or more restrictive

## Common Issues Detected

**Critical Issues:**
- Multiple UID 0 accounts (should only be root)
- Insecure dotfiles in user homes (.netrc, .forward, .rhosts)
- System accounts with login shells
- World-writable directories in root PATH

**Warnings:**
- Missing home directories for interactive users
- Home directories not owned by user
- Insecure home directory permissions (> 750)
- No shell timeout configured
- Weak default umask (< 027)
- Duplicate UIDs, GIDs, or usernames

## Performance Considerations

This role performs extensive checks and may take 30-60 seconds on systems with many users. Key operations:

- Reads `/etc/passwd`, `/etc/shadow`, `/etc/group`
- Runs `chage -l` for each user (can be slow with many users)
- Stats each interactive user's home directory
- Checks for dotfiles in each home directory
- Analyzes root PATH directories

For systems with 100+ users, consider running this role less frequently or during maintenance windows.

## License

Apache-2.0
## Author Information

Created for CIS RHEL 9 compliance automation.
