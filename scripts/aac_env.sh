#!/usr/bin/env bash
# aac_env.sh — export the site's install variables into a shell script.
#
#   source "$(git rev-parse --show-toplevel)/scripts/aac_env.sh"
#   echo "$aac_host"
#
# Reads the [all:vars] section of the operator's install inventory — the same
# file `ansible-playbook -i` reads — so a shell script and a playbook cannot
# disagree about where anything is.
#
# WHY THIS EXISTS
# ---------------
# The playbooks resolve every host and URL through the install inventory. The
# shell scripts under install/, demos/ and scripts/ could not, because bash has
# no `include_vars`, so they carried literal addresses and passwords instead.
# That is the layer a customer actually runs at install time, and it is where
# lab addresses reached them. This closes the gap: one source of truth for both
# languages.
#
# FAIL CLOSED
# -----------
# If no inventory is present this exits non-zero and exports nothing. It
# deliberately does not fall back to a built-in default — a built-in default is
# how a script ends up silently talking to whatever environment the default
# happened to name.
#
# Override the location with AAC_INVENTORY=/path/to/inventory.

_aac_env_load() {
    local root inv
    root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null)" \
        || { echo "aac_env.sh: not inside the AAC repository" >&2; return 1; }

    inv="${AAC_INVENTORY:-$root/install/aac-install-inventory}"

    if [ ! -f "$inv" ]; then
        cat >&2 <<EOF
aac_env.sh: no install inventory at $inv

Create one from the template, then set the values for THIS environment:

    cp install/aac-install-inventory.example install/aac-install-inventory
    \$EDITOR install/aac-install-inventory

Not falling back to a default — a default would point this script at whichever
environment the default named, which is rarely yours.
EOF
        return 1
    fi

    # Parse the [all:vars] block. Skips comments, blank lines and any other
    # INI section. Values are exported verbatim; quotes, if present, are
    # stripped so `key='v'`, `key="v"` and `key=v` behave identically.
    local in_vars=0 line key value
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line%%#*}"
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        [ -z "$line" ] && continue

        case "$line" in
            "[all:vars]") in_vars=1; continue ;;
            "["*"]")      in_vars=0; continue ;;
        esac
        [ "$in_vars" -eq 1 ] || continue
        case "$line" in *=*) ;; *) continue ;; esac

        key="${line%%=*}"
        value="${line#*=}"
        key="${key%"${key##*[![:space:]]}"}"
        value="${value#"${value%%[![:space:]]*}"}"
        case "$value" in
            \'*\') value="${value#\'}"; value="${value%\'}" ;;
            \"*\") value="${value#\"}"; value="${value%\"}" ;;
        esac

        # Only well-formed shell identifiers; anything else is a typo in the
        # inventory and silently exporting it would hide the mistake. The test
        # is a negated class rather than a positive one: a positive pattern
        # like [A-Za-z_][A-Za-z0-9_]* is matched differently by bash and zsh,
        # and under zsh it let `bad-key` through to `export`, which then failed
        # and aborted the whole load. This form behaves the same in both.
        case "$key" in
            ''|*[!A-Za-z0-9_]*|[0-9]*)
                echo "aac_env.sh: skipping malformed key '$key' in $inv" >&2 ;;
            *)
                export "$key=$value" ;;
        esac
    done < "$inv"

    if [ -z "${env_profile:-}" ]; then
        echo "aac_env.sh: env_profile is not set in $inv — refusing to guess." >&2
        return 1
    fi
    return 0
}

_aac_env_load
