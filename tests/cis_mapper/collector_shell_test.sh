#!/usr/bin/env bash
# collector_shell_test.sh — run the CIS supplement blocks of
# ansible/tasks/collect_linux_compliance_facts.yml inside a UBI 9 container
# (podman) against hostile host states and assert none of them yields a pass.
#
# Usage: tests/cis_mapper/collector_shell_test.sh [python-with-pyyaml]
# Needs podman and registry.access.redhat.com/ubi9/ubi. No host is touched.
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
echo '##### end'
EOF

out="$work/out.txt"
podman run --rm -v "$work:/s:Z" registry.access.redhat.com/ubi9/ubi:latest bash /s/scenario.sh > "$out" 2>&1
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
exit $fail
