package cis_windows_2022.main

# AAC consumer bridge — CIS Windows Server 2022
#
# Maps the AAC `opa_framework_map` key `cis_windows_2022` to the policy library's
# canonical entrypoint `cis_windows_server_2022.main`.
#
# WHY THIS FILE EXISTS
# The rego_policy_libraries repo is a standalone library, published Apache-2.0
# and consumable by anyone running OPA or EOPA. It names its entrypoints after
# the packages that hold the policy, not after any one consumer's vocabulary.
# AAC's framework keys are AAC's own; translating them is AAC's job, so this
# alias lives here rather than in the library.
#
# Queried by ansible/playbooks/generic_framework_assessment.yml as
#   /v1/data/cis_windows_2022/main/compliance_report
#
# Deliberately NOT defaulted. If the library entrypoint is missing — a bad
# submodule pin, or a partially loaded OPA container — this rule is undefined
# and OPA returns {}, which the playbook already treats as a hard failure.
# Defaulting it here would convert a loud failure into a silently empty result.

import rego.v1

compliance_report := data.cis_windows_server_2022.main.compliance_report

compliant := data.cis_windows_server_2022.main.compliance_report.compliant

violations := data.cis_windows_server_2022.main.compliance_report.violations
