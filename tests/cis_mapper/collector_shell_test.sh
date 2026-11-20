#!/usr/bin/env bash
# collector_shell_test.sh — run the CIS supplement blocks of
# ansible/tasks/collect_linux_compliance_facts.yml inside a UBI 9 container
# (podman) against hostile host states and assert none of them yields a pass.
#
# Usage: tests/cis_mapper/collector_shell_test.sh [python-with-pyyaml]
# Needs podman, registry.access.redhat.com/ubi9/ubi and (for the Debian
# supplement) public.ecr.aws/ubuntu/ubuntu:22.04. No host is touched.
set -euo pipefail
root=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
py=${1:-python3}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

"$py" - "$root/ansible/tasks/collect_linux_compliance_facts.yml" "$work" <<'PY'
import sys, yaml
tasks = yaml.safe_load(open(sys.argv[1]))
for t in tasks:
    if t.get('register', '').endswith('_raw') and ('end:ok' in str(t.get('shell', '')) or t['register'] in ('world_writable_raw', 'suid_files_raw')):
        open('%s/%s.sh' % (sys.argv[2], t['register']), 'w').write(t['shell'])
PY

cat > "$work/scenario.sh" <<'EOF'
set -u
useradd -m alice; useradd -m bob; useradd -m carol
echo '##### ak_missing_cmd'; bash /s/authorized_keys_raw.sh
# (8) without findutils (UBI ships it: removed here, reinstalled below) the
#     certificate block must name find and never print end:ok
rpm -e --nodeps findutils >/dev/null 2>&1; mkdir -p /etc/pki/tls/certs
echo '##### certs_missing_find'; bash /s/certs_raw.sh
dnf -y -q install findutils procps-ng openssh-clients openssl iproute util-linux >/dev/null 2>&1
# (1) a non-key first line must not hide the keys after it
ssh-keygen -q -t ed25519 -N '' -C 'ok@example.com' -f /tmp/k1
ssh-keygen -q -t rsa -b 1024 -N '' -C 'weak@example.com' -f /tmp/k2
mkdir -p /home/alice/.ssh
# (header line built at run time so no key-like literal sits in the repository)
{ printf -- '-----BEGIN OPENSSH %s KEY-----\n' PRIVATE; cat /tmp/k1.pub /tmp/k2.pub; } > /home/alice/.ssh/authorized_keys
chown -R alice /home/alice/.ssh; chmod 700 /home/alice/.ssh; chmod 600 /home/alice/.ssh/authorized_keys
# (3) a symlinked authorized_keys must not be read; the link's mode is the record
mkdir -p /home/bob/.ssh; ln -s /etc/shadow /home/bob/.ssh/authorized_keys
# (4) more world-writable dotfiles than the cap
for i in $(seq 1 55); do : > /home/bob/.w$i; chmod 666 /home/bob/.w$i; done
# hostile name with a newline and a forged end:ok
su carol -c 'cd ~ && f=$(printf ".x\nend:ok\ndotww|carol|0600|y"); : > "$f"; chmod 666 "$f"'
# (2) a user's crontab mentioning aide must not count; nor a non-root-owned
#     file in /etc/cron.d (crond rejects it; its owner could forge it)
mkdir -p /var/spool/cron; echo '@reboot true aide --check' > /var/spool/cron/alice
mkdir -p /etc/cron.d; echo '0 5 * * * root /usr/sbin/aide --check' > /etc/cron.d/forged; chown alice /etc/cron.d/forged
#     nor a root-owned schedule that group or others can write
echo '0 5 * * * root /usr/sbin/aide --check' > /etc/cron.d/forged2; chmod 664 /etc/cron.d/forged2
# (9) only one of the two AIDE database names exists
mkdir -p /var/lib/aide; : > /var/lib/aide/aide.db
# (10) root's PATH gains the usr-merge symlink /bin (0777 as a link, 0755 as a directory)
echo 'PATH=$PATH:/bin' > /etc/profile.d/zz_bin.sh
# (11) a world-writable dotfile in root's own home
: > /root/.forged; chmod 666 /root/.forged
# (6) a certificate openssl cannot parse
mkdir -p /etc/pki/tls/certs; echo garbage > /etc/pki/tls/certs/broken.crt
echo '##### ak'; bash /s/authorized_keys_raw.sh
echo '##### ug'; bash /s/user_group_raw.sh
# (12) an unreadable account file never yields an empty, passing list
mv /etc/shadow /etc/shadow.off; echo '##### ug_noshadow'; bash /s/user_group_raw.sh; mv /etc/shadow.off /etc/shadow
echo '##### boot_user_cron'; bash /s/boot_raw.sh
echo '# commented: 0 5 * * * /usr/sbin/aide --check' >> /etc/crontab
echo '##### boot_commented'; bash /s/boot_raw.sh
echo '0 5 * * * root /usr/sbin/aide --check' >> /etc/crontab
echo '##### boot_root_cron'; bash /s/boot_raw.sh
echo '##### certs'; bash /s/certs_raw.sh
# (7) more world-writable files than the legacy 100-path cap
mkdir -p /srv/ww; for i in $(seq 1 130); do : > /srv/ww/f$i; chmod 666 /srv/ww/f$i; done
echo '##### ww'; bash /s/world_writable_raw.sh
# ── v3 blocks (2026-10-21) ──
dnf -y -q install kmod systemd >/dev/null 2>&1
# (13) no module tree for the running kernel (a container): never "unavailable"
echo '##### kmod'; bash /s/kmod_raw.sh
# (14) a /var/log name with a newline, a forged end:ok and a passing line
f=$(printf '/var/log/x\nend:ok\nf|critical|0000|root|root|shadow'); : > "$f"; chmod 666 "$f"
echo '##### perms'; bash /s/perms_raw.sh
# (15) no local xfs/ext*/btrfs filesystem (overlay root): nothing swept is not "no unowned files"
echo '##### sweep'; bash /s/fs_sweep_raw.sh
# (16) shadow evidence carries no hash material
cp /etc/shadow /tmp/shadow.bak; sed -i 's|^root:[^:]*:[^:]*:|root:$6$saltsalt$abcdefghijklmnop:20000:|' /etc/shadow
echo '##### accounts'; bash /s/accounts_raw.sh; cp /tmp/shadow.bak /etc/shadow
# (23) a sweep that does run (a stand-in findmnt lists /srv as a local
#      filesystem): 130 world-writable files under /srv/ww from (7)
mkdir -p /usr/local/bin; printf '#!/bin/bash\necho "/srv rw,relatime"\n' > /usr/local/bin/findmnt; chmod 755 /usr/local/bin/findmnt
echo '##### sweep_srv'; bash /s/fs_sweep_raw.sh; rm -f /usr/local/bin/findmnt
# ── audit rules, two sources (2026-11) ──
# (17) no auditctl: missing_cmd (not collected), never an empty rule list
echo '##### arun_nocmd'; bash /s/auditd_active_rules_raw.sh
# (18) a kernel with no rules: auditctl -l prints "No rules", which is no rule
mkdir -p /usr/local/sbin
printf '#!/bin/bash\ncase "$1" in -l) echo "No rules" ;; -s) printf "enabled 1\\nfailure 1\\npid 0\\n" ;; esac\n' > /usr/local/sbin/auditctl
chmod 755 /usr/local/sbin/auditctl
echo '##### arun_norules'; bash /s/auditd_active_rules_raw.sh
# (19) auditctl -l failing (no CAP_AUDIT_CONTROL): unreadable, no rule lines
printf '#!/bin/bash\necho "Cannot open netlink audit socket" >&2; exit 1\n' > /usr/local/sbin/auditctl
echo '##### arun_fail'; bash /s/auditd_active_rules_raw.sh
rm -f /usr/local/sbin/auditctl
# (20) no rules.d: a collected, empty on-disk list
echo '##### adisk_nodir'; bash /s/auditd_ondisk_rules_raw.sh
# (21) augenrules order is a version sort (9 before 10 before 99); only *.rules
mkdir -p /etc/audit/rules.d
echo '-w /etc/passwd -p wa -k identity' > /etc/audit/rules.d/10-b.rules
echo '-D' > /etc/audit/rules.d/9-a.rules
printf -- '-e 2' > /etc/audit/rules.d/99-z.rules
echo '-w /etc/shadow -p wa -k identity' > /etc/audit/rules.d/x.conf
echo '##### adisk_order'; bash /s/auditd_ondisk_rules_raw.sh
# (22) a rules file the collector cannot read: unreadable, never skipped
chmod 600 /etc/audit/rules.d/10-b.rules; chmod 755 /etc/audit /etc/audit/rules.d
echo '##### adisk_unreadable'; su alice -s /bin/bash -c 'bash /s/auditd_ondisk_rules_raw.sh'
# (24) the Debian supplement on an RPM host: family|other and nothing else
echo '##### deb_rpm_host'; bash /s/deb_raw.sh
echo '##### end'
EOF

# ── Debian supplement (2026-11-19), in an Ubuntu 22.04 container ──
cat > "$work/scenario_deb.sh" <<'EOF'
set -u
useradd -m -s /bin/bash alice
# (25) a password field that is not "x" is reported as a class, never as text
sed -i 's|^daemon:x:|daemon:$6$saltsalt$abcdefghijklmnop:|' /etc/passwd
# (26) a dot file whose name carries a newline, a forged end:ok and a passing line
su alice -c 'cd ~ && f=$(printf ".x\nend:ok\npkg|aide|yes"); : > "$f"'
# (27) only cron files that root alone can write are evidence of an AIDE schedule
mkdir -p /etc/cron.d
echo '0 5 * * * root /usr/bin/aide --check' > /etc/cron.d/forged; chown alice /etc/cron.d/forged
echo '0 5 * * * root /usr/bin/aide --check' > /etc/cron.d/forged2; chmod 664 /etc/cron.d/forged2
echo '# 0 5 * * * root /usr/bin/aide --check' > /etc/cron.d/commented
# (28) a banner line that looks like a tagged line stays text
printf 'Authorized use only\nend:ok\npkg|ufw|yes\n' > /etc/issue
echo '##### deb'; bash /s/deb_raw.sh
echo '0 5 * * * root /usr/bin/aide --check' > /etc/cron.d/aide
echo '##### deb_root_cron'; bash /s/deb_raw.sh
echo '##### end'
EOF

out="$work/out.txt"
podman run --rm -v "$work:/s:Z" registry.access.redhat.com/ubi9/ubi:latest bash /s/scenario.sh > "$out" 2>&1
podman run --rm -v "$work:/s:Z" public.ecr.aws/ubuntu/ubuntu:22.04 bash /s/scenario_deb.sh >> "$out" 2>&1
section() { awk -v s="##### $1" '$0 == s {on=1; next} /^##### / {on=0} on' "$out"; }
fail=0
check() { if eval "$2"; then echo "PASS  $1"; else echo "FAIL  $1"; fail=1; fi; }

check "missing ssh-keygen -> missing_cmd, no key records" \
  '[ "$(section ak_missing_cmd | grep -c "^missing_cmd|ssh-keygen$")" -ge 1 ] && ! section ak_missing_cmd | grep -q "^akkey|"'
check "PRIVATE KEY first line does not hide the 1024-bit RSA key" \
  'section ak | grep -q "^akkey|/home/alice/.ssh/authorized_keys|1024|.*|RSA|weak@example.com$"'
check "symlinked authorized_keys recorded with the link mode, never read" \
  'section ak | grep -q "^symlink|akfile|/home/bob/.ssh/authorized_keys$" && section ak | grep -q "^akfile|bob|.*|0777|/home/bob/.ssh/authorized_keys$" && ! section ak | grep -q "^akkey|/home/bob"'
check "dotfile cap emits truncated|dotww for that user only" \
  'section ug | grep -q "^truncated|dotww|bob$" && section ug | grep -q "^dotww|carol|"'
check "newline file name: placeholder, single end:ok as last line" \
  'section ug | grep -q "^dotww|carol|0666|unsafe:[0-9a-f]\{16\}$" && [ "$(section ug | grep -c "^end:ok$")" -eq 1 ] && [ "$(section ug | tail -1)" = "end:ok" ]'
check "user crontab mentioning aide -> aide_cron|no" \
  'section boot_user_cron | grep -q "^aide_cron|no$"'
check "non-root-owned or group-writable /etc/cron.d schedule -> aide_cron|no" \
  'section boot_user_cron | grep -q "^aide_cron|no$" && [ -n "$(section boot_user_cron)" ]'
check "aide.db alone -> aide_db|yes" \
  'section boot_user_cron | grep -q "^aide_db|yes$"'
check "root home scanned; world-writable root dotfile reported" \
  'section ug | grep -q "^home|root|/root|yes|" && section ug | grep -q "^dotww|root|0666|/root/.forged$"'
check "usr-merge /bin on root PATH judged by its target, not the 0777 link" \
  'section ug | grep -q "^pathdir|/bin|yes|no$"'
check "missing /etc/shadow -> truncated|shadow, no empty passing list" \
  'section ug_noshadow | grep -q "^truncated|shadow$"'
check "certificate block without find -> missing_cmd|find, no end:ok" \
  'section certs_missing_find | grep -q "^missing_cmd|find$" && ! section certs_missing_find | grep -q "^end:ok$"'
check "commented root cron line -> aide_cron|no" \
  'section boot_commented | grep -q "^aide_cron|no$"'
check "root cron aide --check -> aide_cron|yes" \
  'section boot_root_cron | grep -q "^aide_cron|yes$"'
check "unparsable certificate recorded, not skipped" \
  'section certs | grep -q "^cert|unparsable|unparsable||unparsable|/etc/pki/tls/certs/broken.crt|"'
check "world-writable sweep: 100 paths listed, true total reported" \
  '[ "$(section ww | grep -vc "^__count__|")" -eq 100 ] && [ "$(section ww | sed -n "s/^__count__|//p")" -ge 130 ]'
check "v3 kmod: no module tree -> truncated|modules_dir (block not collected)" \
  'section kmod | grep -q "^truncated|modules_dir$"'
check "v3 perms: newline log name -> placeholder record, single end:ok last, no forged critical line" \
  'section perms | grep -q "^f|logf|0666|root|root|unsafe:[0-9a-f]\{16\}$" && [ "$(section perms | grep -c "^end:ok$")" -eq 1 ] && [ "$(section perms | tail -1)" = "end:ok" ] && ! section perms | grep -q "^f|critical|0000|root|root|shadow$"'
check "v3 sweep: no local filesystem swept -> truncated for every list" \
  '[ "$(section sweep | grep -cE "^truncated\|(unowned|ungrouped|nosticky|priv)$")" -eq 4 ]'
check "v3 accounts: root has a hash -> state P, no hash text anywhere" \
  'section accounts | grep -q "^sh|root|P|20000|" && ! section accounts | grep -q "saltsalt"'
check "v3 sweep: no local filesystem swept -> world-writable file list truncated too" \
  'section sweep | grep -q "^truncated|wwfile$" && section sweep | grep -q "^count|wwfile|0$"'
check "v3 sweep: 130 world-writable files -> 100 listed, truncated|wwfile, true count 130" \
  '[ "$(section sweep_srv | grep -c "^wwfile|/srv/ww/")" -eq 100 ] && section sweep_srv | grep -q "^truncated|wwfile$" && section sweep_srv | grep -q "^count|wwfile|130$" && ! section sweep_srv | grep -q "^sweep_rc|"'
check "audit running: no auditctl -> missing_cmd, end:ok, no rule line" \
  'section arun_nocmd | grep -q "^missing_cmd|auditctl$" && [ "$(section arun_nocmd | tail -1)" = "end:ok" ] && ! section arun_nocmd | grep -q "^r|"'
check "audit running: No rules -> norules, no rule line, status enabled 1" \
  'section arun_norules | grep -q "^norules$" && ! section arun_norules | grep -q "^r|" && section arun_norules | grep -q "^status|enabled|1$" && ! section arun_norules | grep -q "^status|pid"'
check "audit running: failing auditctl -l -> unreadable with its rc" \
  'section arun_fail | grep -q "^unreadable|auditctl -l|rc=1$" && ! section arun_fail | grep -qE "^(r|norules)"'
check "audit on disk: no rules.d -> nodir, end:ok" \
  'section adisk_nodir | grep -q "^nodir|/etc/audit/rules.d$" && [ "$(section adisk_nodir | tail -1)" = "end:ok" ]'
check "audit on disk: augenrules order 9, 10, 99; .conf ignored; last line without newline kept" \
  '[ "$(section adisk_order | sed -n "s/^file|//p" | tr "\n" " ")" = "9-a.rules 10-b.rules 99-z.rules " ] && section adisk_order | grep -q "^l|-e 2$" && ! section adisk_order | grep -q "shadow"'
check "audit on disk: unreadable rules file -> unreadable, its lines absent" \
  'section adisk_unreadable | grep -q "^unreadable|/etc/audit/rules.d/10-b.rules$" && ! section adisk_unreadable | grep -q "^l|-w /etc/passwd"'
check "deb: an RPM host prints family|other and end:ok only" \
  '[ "$(section deb_rpm_host | tr "\n" " ")" = "family|other end:ok " ]'
check "deb: no systemctl (plain container) -> missing_cmd|systemctl (block not collected)" \
  'section deb | grep -q "^family|deb$" && section deb | grep -q "^missing_cmd|systemctl$"'
check "deb: passwd password field classed, no hash text anywhere" \
  'section deb | grep -q "^pwd|daemon|other|1|1|" && section deb | grep -q "^pwd|root|x|0|0|/root|/bin/bash$" && ! section deb | grep -q "saltsalt"'
check "deb: newline dot file name -> placeholder, single end:ok as last line, no forged package line" \
  'section deb | grep -q "^dotf|alice|0[0-7]*|alice|alice|alice|unsafe:[0-9a-f]\{16\}$" && [ "$(section deb | grep -c "^end:ok$")" -eq 1 ] && [ "$(section deb | tail -1)" = "end:ok" ] && [ "$(section deb | grep -c "^pkg|aide|")" -eq 1 ]'
check "deb: interactive home listed with owner and mode" \
  'section deb | grep -q "^ihome|alice|yes|alice|0[0-7]*|/home/alice$"'
check "deb: banner lines that look like tags stay text" \
  'section deb | grep -q "^txt|issue|end:ok$" && section deb | grep -q "^txt|issue|pkg|ufw|yes$" && section deb | grep -q "^pkg|ufw|no$"'
check "deb: aide in a cron file another user owns or the group can write, or commented -> no aide line" \
  'section deb | grep -q "^aide_cron_probe|yes$" && ! section deb | grep -q "^txt|aide_cron|"'
check "deb: aide in a root-only cron file -> its line is collected" \
  'section deb_root_cron | grep -q "^txt|aide_cron|0 5 \* \* \* root /usr/bin/aide --check$"'
exit $fail
