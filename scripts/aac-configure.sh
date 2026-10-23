#!/usr/bin/env bash
# aac-configure.sh — first step of any AAC install.
#
#   ./scripts/aac-configure.sh
#
# Creates the three operator-owned config files from their tracked templates,
# then tells you what to edit. Safe to re-run: it never overwrites a file you
# already have.
#
# WHY THIS STEP EXISTS
# --------------------
# None of these files are in git, deliberately. They hold the addresses and
# passwords of one specific environment, and a filled-in copy in git is how one
# site's infrastructure ends up in another site's install. This project shipped
# a tracked `site_config.yml` pointing at the Red Hat lab for months, and every
# clone inherited it.
#
# This is the same contract the AAP containerized installer has: it ships
# `inventory-growth` as a template and refuses to run until you have made your
# own `inventory` from it. A missing config file is a clear failure. A config
# file quietly full of someone else's addresses is not.

set -euo pipefail

root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
cd "$root"

created=0
kept=0

# template → destination
copy_if_absent() {
    local src="$1" dst="$2"
    if [ ! -f "$src" ]; then
        echo "  ERROR: template missing: $src" >&2
        return 1
    fi
    if [ -f "$dst" ]; then
        echo "  kept     $dst (already exists — not overwritten)"
        kept=$((kept + 1))
    else
        cp "$src" "$dst"
        echo "  created  $dst"
        created=$((created + 1))
    fi
}

echo "AAC configure — creating operator-owned config from templates"
echo

copy_if_absent install/aac-install-inventory.example install/aac-install-inventory
copy_if_absent ansible/vars/site_config.yml.example  ansible/vars/site_config.yml
copy_if_absent ansible/vars/vault_secrets.yml.example ansible/vars/vault_secrets.yml

echo
echo "$created created, $kept already present."
echo

if [ "$created" -gt 0 ]; then
    cat <<'EOF'
NEXT — edit these before running anything:

  1. install/aac-install-inventory
     Every host, IP and URL for THIS environment. Start with `env_profile`
     (customer | lab | macaap | rhpds) and `aac_host`. On a single-node
     install those two may be the only lines you change.

  2. ansible/vars/vault_secrets.yml
     Passwords, if you are running from the CLI. Encrypt it afterwards:
         ansible-vault encrypt ansible/vars/vault_secrets.yml
     Running through AAP instead? Leave it alone and attach an AAP credential
     — that is the better answer for anything production, and nothing
     sensitive touches the filesystem.

  3. ansible/vars/site_config.yml
     Optional. Machine-local overrides on top of the inventory. Most installs
     never need to touch it.

Then:

     ansible-playbook -i install/aac-install-inventory \
         ansible/playbooks/install_preflight.yml

  Preflight checks what must already be true before installing, and names
  anything that is not.

All three files are gitignored. They should never appear in a commit.
EOF
else
    echo "Nothing to do — all three config files already exist."
fi
