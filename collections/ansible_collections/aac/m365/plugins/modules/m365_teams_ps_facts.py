#!/usr/bin/python
# -*- coding: utf-8 -*-
"""m365_teams_ps_facts — collect CIS M365 v7.0.0 Section 8 state.

16 of section 8's 17 recommendations are audited through Teams
PowerShell. All four cmdlets the benchmark names were verified present in
the aac-m365-ee image before this collector was written.

  Get-CsTeamsClientConfiguration      8.1.1, 8.1.2
  Get-CsTenantFederationConfiguration 8.2.1, 8.2.2, 8.2.3, 8.2.4
  Get-CsTeamsMeetingPolicy            8.5.1 - 8.5.9
  Get-CsTeamsMessagingPolicy          8.6.1

NOT collected: 8.4.1 (app permission policies). CIS marks it Manual and
names no cmdlet. Get-CsTeamsAppPermissionPolicy plausibly covers it, but
that is an assumption -- it stays in the attestation module's unresolved
set until a live-tenant probe settles it.

The meeting and messaging policies are COLLECTIONS. A tenant can hold
many, and a user is governed by the one assigned to them. The Global
policy is the tenant default and is what the benchmark audits, but every
policy is collected so the evaluation can report a permissive non-global
policy rather than passing on Global alone.
"""
from __future__ import absolute_import, division, print_function

__metaclass__ = type


DOCUMENTATION = r"""
---
module: m365_teams_ps_facts
short_description: Collect Microsoft Teams state for CIS v7.0.0 Section 8
description:
  - Connects to Microsoft Teams PowerShell app-only with a certificate and
    collects the state CIS Microsoft 365 Foundations Benchmark v7.0.0
    Section 8 evaluates.
  - Requires an execution environment carrying pwsh and the MicrosoftTeams
    module (see aac-m365-ee).
  - Facts that cannot be collected are reported in C(unavailable).
options:
  app_id:
    description: Application (client) ID of the Entra app registration.
    required: true
    type: str
  tenant_id:
    description: Entra tenant GUID.
    required: true
    type: str
  organization:
    description: Tenant organization name, e.g. contoso.onmicrosoft.com.
    required: true
    type: str
  certificate_thumbprint:
    description:
      - Thumbprint of the certificate used for app-only auth.
      - Connect-MicrosoftTeams takes a thumbprint rather than a PFX path,
        so the certificate must be present in the runtime's store.
    required: true
    type: str
  timeout:
    description: Seconds to allow each PowerShell invocation.
    type: int
    default: 300
author:
  - "AAC maintainers"
"""

EXAMPLES = r"""
- name: Collect Teams state for CIS v7.0.0 Section 8
  aac.m365.m365_teams_ps_facts:
    app_id: "{{ m365_client_id }}"
    tenant_id: "{{ m365_tenant_id }}"
    organization: "{{ m365_organization }}"
    certificate_thumbprint: "{{ m365_cert_thumbprint }}"
  register: teams_ps
"""

RETURN = r"""
facts:
  description: Section 8 tenant state.
  returned: always
  type: dict
"""

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.aac.m365.plugins.module_utils.pwsh import (
    PwshRunner,
    PwshError,
)

QUERIES = {
    "client_configuration": (
        "Get-CsTeamsClientConfiguration | Select-Object "
        "Identity, AllowDropBox, AllowBox, AllowGoogleDrive, AllowShareFile, "
        "AllowEgnyte, AllowEmailIntoChannel",
        ["8.1.1", "8.1.2"],
    ),
    "federation_configuration": (
        "Get-CsTenantFederationConfiguration | Select-Object "
        "Identity, AllowFederatedUsers, AllowPublicUsers, "
        "AllowTeamsConsumer, AllowTeamsConsumerInbound, "
        "AllowedDomains, BlockedDomains, "
        "ExternalAccessWithTrialTenants",
        ["8.2.1", "8.2.2", "8.2.3", "8.2.4"],
    ),
    "meeting_policies": (
        "@(Get-CsTeamsMeetingPolicy | Select-Object "
        "Identity, AllowAnonymousUsersToJoinMeeting, "
        "AllowAnonymousUsersToStartMeeting, AutoAdmittedUsers, "
        "AllowPSTNUsersToBypassLobby, MeetingChatEnabledType, "
        "DesignatedPresenterRoleMode, AllowExternalParticipantGiveRequestControl, "
        "AllowRecordingAndTranscription, AllowCloudRecording)",
        ["8.5.1", "8.5.2", "8.5.3", "8.5.4", "8.5.5", "8.5.6", "8.5.7", "8.5.8", "8.5.9"],
    ),
    "messaging_policies": (
        "@(Get-CsTeamsMessagingPolicy | Select-Object "
        "Identity, AllowSecurityEndUserReporting)",
        ["8.6.1"],
    ),
}


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def collect_facts(runner):
    facts, unavailable = {}, {}

    for key, (snippet, _controls) in QUERIES.items():
        value, err = runner.try_run(snippet)
        if err:
            unavailable[key] = err
            continue
        if key.endswith("_policies"):
            rows = _as_list(value)
            facts[key] = rows
            # The Global policy is the tenant default and is what the
            # benchmark audits; surface it directly so the evaluation does
            # not have to rediscover which row that is.
            facts[key + "_global"] = next(
                (r for r in rows
                 if str(r.get("Identity", "")).lower() in ("global", "tag:global")),
                None,
            )
        else:
            facts[key] = value

    facts["unavailable"] = unavailable
    facts["collected"] = True
    facts["source"] = "teams_powershell"
    return facts


def main() -> None:
    module = AnsibleModule(
        argument_spec=dict(
            app_id=dict(type="str", required=True),
            tenant_id=dict(type="str", required=True),
            organization=dict(type="str", required=True),
            certificate_thumbprint=dict(type="str", required=True),
            timeout=dict(type="int", default=300),
        ),
        supports_check_mode=True,
    )
    if module.check_mode:
        module.exit_json(changed=False, facts={})
    try:
        runner = PwshRunner(
            service="teams",
            app_id=module.params["app_id"],
            tenant_id=module.params["tenant_id"],
            organization=module.params["organization"],
            cert_thumbprint=module.params["certificate_thumbprint"],
            timeout=module.params["timeout"],
        )
        facts = collect_facts(runner)
    except PwshError as exc:
        module.fail_json(msg=str(exc), stderr=exc.stderr[:2000])
        return
    module.exit_json(changed=False, facts=facts)


if __name__ == "__main__":
    main()
