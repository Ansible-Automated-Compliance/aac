#!/bin/bash
#
# install_eda.sh — DEPRECATED
#
# This script installed Event Driven Ansible (EDA) onto a PRE-containerized AAP
# using the legacy `./setup.sh -e eda_install=true` bundle installer and an
# [automationedacontroller] inventory block. That approach does NOT apply to
# AAP 2.6.
#
# On AAP 2.6, EDA (the Event-Driven Ansible controller) is a COMPONENT of the
# containerized / OpenShift-operator install — there is no separate EDA
# installer step. See:
#   https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/html/containerized_installation
#
# AAC's EDA content is configured on the already-running AAP, not installed here:
#   - Rulebooks:            extensions/eda/rulebooks/
#   - Seed an activation:   the aac-demos repo: demos/sentinel/playbooks/seed_eda_sentinel_activation.yml
#                           (and the golden-image / AMI EDA seeders)
#   - After a rulebook change: sync the AAP project, then RESTART the activation
#                           (sync alone does not refresh running rulebook content)
#
# This file is retained only to explain the migration; it performs no install.

cat <<'EOF'

  install_eda.sh is DEPRECATED and does nothing.

  On AAP 2.6, EDA ships with the containerized AAP install — there is no
  separate EDA installer step.

  To configure AAC's EDA content on a running AAP 2.6:
    * Rulebooks live in:  extensions/eda/rulebooks/
    * Seed an activation: the aac-demos repo: demos/sentinel/playbooks/seed_eda_sentinel_activation.yml
    * After changing a rulebook: sync the AAP project, then RESTART the
      activation (sync alone does not update running rulebook content).

  See: docs (containerized AAP 2.6 installation) linked at the top of this file.

EOF

exit 0
