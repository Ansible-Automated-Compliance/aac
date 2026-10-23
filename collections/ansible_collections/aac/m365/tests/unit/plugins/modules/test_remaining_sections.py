"""Unit tests for the Section 2/3/5/6/7 fact modules.

All five modules follow the same Secure Score projection pattern,
so the test surface compresses cleanly: one test class per module,
each pinning that:

  - Only the module's relevant control IDs are projected into the
    fact set (noise is filtered).
  - `controls_by_id` reflects the implementation_status.
  - Section-specific endpoints (when present) are read and shaped
    into the documented fact fields.
  - Endpoint 403 falls back to safe defaults, doesn't fail the
    module.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]
COLLECTIONS_PATH = REPO_ROOT / "collections"
if str(COLLECTIONS_PATH) not in sys.path:
    sys.path.insert(0, str(COLLECTIONS_PATH))


class FakeGraphClient:
    def __init__(self, responses: dict, raises: set | None = None):
        self.responses = responses
        self.raises = raises or set()

    def _resolve(self, path: str):
        if path in self.raises:
            from ansible_collections.aac.m365.plugins.module_utils.graph import GraphError
            raise GraphError(403, "synthetic forbidden", path)
        if path not in self.responses:
            raise AssertionError(f"unexpected call: {path}")
        return self.responses[path]

    def get(self, path: str, params=None):
        if (
            path.startswith("/security/secureScoreControlProfiles/")
            and path not in self.responses
            and path not in self.raises
        ):
            from ansible_collections.aac.m365.plugins.module_utils.graph import GraphError
            raise GraphError(404, "not found", path)
        return self._resolve(path)

    def get_all(self, path: str, params=None):
        return self._resolve(path)


def _ss_row(cid: str, status: str) -> dict:
    return {
        "id": cid,
        "title": cid,
        "implementationStatus": status,
        "maxScore": 5,
        "tier": "Defender",
        "service": "MicrosoftDefender",
    }


def _stub_secure_score(responses: dict, rows: list[dict]) -> None:
    for row in rows:
        cid = row["id"]
        responses[f"/security/secureScoreControlProfiles/{cid}"] = row


# ── Defender ─────────────────────────────────────────────────────────


from ansible_collections.aac.m365.plugins.modules import m365_defender_facts


class TestDefender:
    def test_relevant_controls_projected(self):
        responses = {
            "/security/secureScores": {"value": [{"currentScore": 600, "maxScore": 1000}]},
        }
        _stub_secure_score(
            responses,
            [
                _ss_row("ATPSafeAttachments", "Implemented"),
                _ss_row("AntiPhishPolicy", "NotImplemented"),
                _ss_row("UnrelatedControl", "Implemented"),
            ],
        )
        facts = m365_defender_facts.collect_facts(FakeGraphClient(responses))
        ids = {c["id"] for c in facts["secure_score_controls"]}
        assert "ATPSafeAttachments" in ids
        assert "AntiPhishPolicy" in ids
        assert "UnrelatedControl" not in ids

    def test_controls_by_id_reflects_status(self):
        responses = {"/security/secureScores": {"value": []}}
        _stub_secure_score(
            responses,
            [
                _ss_row("ATPSafeAttachments", "Implemented"),
                _ss_row("AntiPhishPolicy", "NotImplemented"),
            ],
        )
        facts = m365_defender_facts.collect_facts(FakeGraphClient(responses))
        assert facts["controls_by_id"]["ATPSafeAttachments"] == "Implemented"
        assert facts["controls_by_id"]["AntiPhishPolicy"] == "NotImplemented"

    def test_secure_scores_403_yields_null_latest(self):
        responses = {}
        raises = {"/security/secureScores"}
        facts = m365_defender_facts.collect_facts(FakeGraphClient(responses, raises))
        assert facts["latest_score"] is None


# ── Purview ──────────────────────────────────────────────────────────


from ansible_collections.aac.m365.plugins.modules import m365_purview_facts


class TestPurview:
    def test_audit_log_accessible_flag(self):
        responses = {
            "/auditLogs/directoryAudits": {
                "value": [{"activityDateTime": "2026-06-06T00:00:00Z"}],
            },
            "/security/cases/ediscoveryCases": {"value": []},
        }
        facts = m365_purview_facts.collect_facts(FakeGraphClient(responses))
        # audit_log_accessible is no longer derived from /auditLogs/directoryAudits
        # (that made CIS 3.1.1 a false pass). It is emitted as None so the policy
        # reports 3.1.1 as not-evaluated; the timestamp remains a retention hint.
        assert facts["audit_log_accessible"] is None
        assert facts["audit_log_most_recent"] == "2026-06-06T00:00:00Z"

    def test_audit_log_403_yields_false_flag(self):
        responses = {
            "/security/cases/ediscoveryCases": {"value": []},
        }
        raises = {"/auditLogs/directoryAudits"}
        facts = m365_purview_facts.collect_facts(FakeGraphClient(responses, raises))
        # Emitted as None regardless of directoryAudits (see above) -- fail-closed.
        assert facts["audit_log_accessible"] is None

    def test_ediscovery_count(self):
        responses = {
            "/auditLogs/directoryAudits": {"value": []},
            "/security/cases/ediscoveryCases": {
                "value": [{"id": "case-1"}, {"id": "case-2"}],
            },
        }
        facts = m365_purview_facts.collect_facts(FakeGraphClient(responses))
        assert facts["ediscovery_cases_count"] == 2


# ── Fabric ───────────────────────────────────────────────────────────


from ansible_collections.aac.m365.plugins.modules import m365_fabric_facts


class TestFabric:
    def test_controls_evaluable_count(self):
        responses = {}
        _stub_secure_score(
            responses,
            [
                _ss_row("FabricGuestUserAccess", "Implemented"),
                _ss_row("FabricExternalSharing", "NotImplemented"),
                _ss_row("FabricServicePrincipalSignIn", "Implemented"),
            ],
        )
        facts = m365_fabric_facts.collect_facts(FakeGraphClient(responses))
        assert facts["controls_evaluable"] == 3
        assert facts["graph_only_coverage"] is True


# ── SharePoint ───────────────────────────────────────────────────────


from ansible_collections.aac.m365.plugins.modules import m365_sharepoint_facts


class TestSharePoint:
    def test_admin_settings_pulled_when_reachable(self):
        responses = {
            "/admin/sharepoint/settings": {
                "sharingCapability": "ExternalUserAndGuestSharing",
                "defaultSharingLinkType": "AnonymousAccess",
                "legacyAuthProtocolsEnabled": False,
            },
        }
        facts = m365_sharepoint_facts.collect_facts(FakeGraphClient(responses))
        assert facts["sharing_capability"] == "ExternalUserAndGuestSharing"
        assert facts["default_sharing_link_type"] == "AnonymousAccess"
        assert facts["legacy_auth_protocols_enabled"] is False
        assert facts["settings_reachable"] is True

    def test_admin_settings_403_falls_back_to_secure_score_only(self):
        responses = {
            "/admin/sharepoint/settings": {},
        }
        raises = {"/admin/sharepoint/settings"}
        facts = m365_sharepoint_facts.collect_facts(FakeGraphClient(responses, raises))
        assert facts["settings_reachable"] is False
        assert facts["sharing_capability"] is None


# ── Teams ────────────────────────────────────────────────────────────


from ansible_collections.aac.m365.plugins.modules import m365_teams_facts


class TestTeams:
    def test_teams_apps_count(self):
        responses = {
            "/appCatalogs/teamsApps": {
                "value": [{"id": f"app-{i}"} for i in range(7)],
            },
        }
        facts = m365_teams_facts.collect_facts(FakeGraphClient(responses))
        assert facts["teams_apps_count"] == 7

    def test_teams_apps_403_yields_zero(self):
        responses = {}
        raises = {"/appCatalogs/teamsApps"}
        facts = m365_teams_facts.collect_facts(FakeGraphClient(responses, raises))
        assert facts["teams_apps_count"] == 0
