#!/usr/bin/python
# -*- coding: utf-8 -*-
"""m365_purview_ps_facts — collect CIS M365 v7.0.0 Section 3 state.

Section 3's DLP and sensitivity-label controls are audited through
Security & Compliance PowerShell, which is a DIFFERENT endpoint from
Exchange Online PowerShell despite shipping in the same module. It needs
its own session via Connect-IPPSSession.

  Get-DlpCompliancePolicy   3.2.1, 3.2.2, 3.2.3
  Get-LabelPolicy           3.3.1

3.1.1 (unified audit log) is not here -- it is already collected from
Graph on the Purview facts path.

DLP policy workload scoping matters for these controls: 3.2.1 asks
whether DLP is enabled at all, 3.2.2 whether it covers Teams, and 3.2.3
whether it is published for Copilot. Those are distinguished by the
policy's workload and location fields, not by separate policies, so the
raw fields are collected and the Rego decides.
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""
---
module: m365_purview_ps_facts
short_description: Collect Microsoft Purview DLP and label state for CIS v7.0.0 Section 3
description:
  - Connects to Security & Compliance PowerShell app-only with a
    certificate (Connect-IPPSSession) and collects the DLP and
    sensitivity-label state CIS Microsoft 365 Foundations Benchmark
    v7.0.0 Section 3 evaluates.
  - Security & Compliance PowerShell is a separate endpoint from Exchange
    Online PowerShell and requires its own session.
  - Facts that cannot be collected are reported in C(unavailable).
options:
  app_id:
    description: Application (client) ID of the Entra app registration.
    required: true
    type: str
  organization:
    description: Tenant organization name, e.g. contoso.onmicrosoft.com.
    required: true
    type: str
  certificate_path:
    description: Path to the PFX certificate used for app-only auth.
    required: true
    type: str
  certificate_password:
    description: Password protecting the PFX certificate.
    required: true
    type: str
    no_log: true
  timeout:
    description: Seconds to allow each PowerShell invocation.
    type: int
    default: 300
author:
  - "AAC maintainers"
"""

EXAMPLES = r"""
- name: Collect Purview DLP state for CIS v7.0.0 Section 3
  aac.m365.m365_purview_ps_facts:
    app_id: "{{ m365_client_id }}"
    organization: "{{ m365_organization }}"
    certificate_path: "{{ m365_cert_path }}"
    certificate_password: "{{ m365_cert_password }}"
  register: purview_ps
"""

RETURN = r"""
facts:
  description: Section 3 DLP and label state.
  returned: always
  type: dict
"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.aac.m365.plugins.module_utils.pwsh import (
    PwshRunner,
    PwshError,
)

QUERIES = {
    "dlp_policies": (
        "@(Get-DlpCompliancePolicy | Select-Object Name, Mode, Enabled, "
        "Workload, TeamsLocation, ExchangeLocation, SharePointLocation, "
        "OneDriveLocation, EndpointDlpLocation, Comment)",
        ["3.2.1", "3.2.2", "3.2.3"],
    ),
    "label_policies": (
        "@(Get-LabelPolicy | Select-Object Name, Mode, Enabled, "
        "Workload, Labels, ExchangeLocation)",
        ["3.3.1"],
    ),
}


def collect_facts(runner):
    facts, unavailable = {}, {}
    for key, (snippet, controls) in QUERIES.items():
        value, err = runner.try_run(snippet)
        if err:
            unavailable[key] = "%s (blocks %s)" % (err, ", ".join(controls))
        else:
            facts[key] = value if isinstance(value, list) else [value]

    facts["unavailable"] = unavailable
    facts["collected"] = True
    facts["source"] = "security_compliance_powershell"
    return facts


def main() -> None:
    module = AnsibleModule(
        argument_spec=dict(
            app_id=dict(type="str", required=True),
            organization=dict(type="str", required=True),
            certificate_path=dict(type="str", required=True),
            certificate_password=dict(type="str", required=True, no_log=True),
            timeout=dict(type="int", default=300),
        ),
        supports_check_mode=True,
    )
    if module.check_mode:
        module.exit_json(changed=False, facts={})
    try:
        runner = PwshRunner(
            service="purview",
            app_id=module.params["app_id"],
            organization=module.params["organization"],
            cert_path=module.params["certificate_path"],
            cert_password=module.params["certificate_password"],
            timeout=module.params["timeout"],
        )
        facts = collect_facts(runner)
    except PwshError as exc:
        module.fail_json(msg=str(exc), stderr=exc.stderr[:2000])
        return
    module.exit_json(changed=False, facts=facts)


if __name__ == "__main__":
    main()
