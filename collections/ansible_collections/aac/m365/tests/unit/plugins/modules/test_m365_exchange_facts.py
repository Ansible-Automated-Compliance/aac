"""Unit tests for m365_exchange_facts.

Mocks GraphClient. Pins:

  - Initial .onmicrosoft.com domains are excluded from customer
    DNS-hygiene checks (CIS 4.5/4.6/4.7 apply to customer-owned
    domains).
  - SPF / DKIM / DMARC are read from PUBLISHED DNS (TXT v=spf1 at the
    domain, TXT v=DMARC1 at _dmarc, CNAME at selectorN._domainkey), and
    a lookup that fails or a missing DNS library is dns_unavailable.
  - Mailbox audit aggregate: distinguishes evaluable
    (mailboxAuditEnabled key present) from non-evaluable.
  - Per-user mailbox 4xx falls back to skipping the user, not
    failing the assessment (some users have no Exchange license).
  - Secure Score control rows are projected to just the relevant
    set.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[5]
COLLECTIONS_PATH = REPO_ROOT / "collections"
if str(COLLECTIONS_PATH) not in sys.path:
    sys.path.insert(0, str(COLLECTIONS_PATH))


from ansible_collections.aac.m365.plugins.modules import m365_exchange_facts


class FakeGraphClient:
    """Stub matching the identity-facts test pattern."""

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


# Minimal response set — every test extends this with whatever the
# specific scenario needs. `domain_dns` maps a domain to its PUBLISHED
# records for FakeResolver; Graph's serviceConfigurationRecords (the
# records Microsoft requires) is deliberately no longer read.
def _baseline(domain_rows, domain_dns, user_rows, user_mailbox):
    responses = {
        "/domains": domain_rows,
        # /users is fetched with a single-page `get` (not get_all), so it
        # returns the real Graph page shape: {"value": [...]}.
        "/users": {"value": user_rows},
        "/organization": {"value": [{"displayName": "Acme", "tenantType": "AAD"}]},
    }
    for uid, settings in user_mailbox.items():
        responses[f"/users/{uid}/mailboxSettings"] = settings
    return responses


class FakeResolver:
    """Published DNS keyed by (name, rtype). Unknown names do not exist
    (NXDOMAIN -> []); names in `failing` raise like a timeout would."""

    def __init__(self, records=None, failing=()):
        self.records = records or {}
        self.failing = set(failing)
        self.queries = []

    def query(self, name, rtype):
        self.queries.append((name, rtype))
        if name in self.failing:
            raise m365_exchange_facts.DnsLookupError("DNS lookup for %s %s timed out" % (rtype, name))
        return list(self.records.get((name, rtype), []))


PUBLISHED_OK = {
    ("acme.com", "TXT"): ["v=spf1 include:spf.protection.outlook.com -all", "google-site-verification=x"],
    ("_dmarc.acme.com", "TXT"): ["v=DMARC1; p=reject"],
    ("selector1._domainkey.acme.com", "CNAME"): ["selector1-acme-com._domainkey.acme.onmicrosoft.com."],
}


def _collect(responses, resolver=None, dns_error=None, raises=None):
    return m365_exchange_facts.collect_facts(
        FakeGraphClient(responses, raises), resolver=resolver, dns_error=dns_error)


# ── Published DNS (2.1.8 / 2.1.9 / 2.1.10) ──────────────────────────


def test_initial_domain_is_excluded_and_not_looked_up():
    """The default acme.onmicrosoft.com is is_initial=true; the policy skips
    it and the tenant cannot publish DNS for it, so nothing is queried."""
    responses = _baseline(
        domain_rows=[
            {"id": "acme.onmicrosoft.com", "isVerified": True, "isInitial": True, "isDefault": True},
            {"id": "acme.com", "isVerified": True, "isInitial": False},
        ],
        domain_dns={}, user_rows=[], user_mailbox={},
    )
    resolver = FakeResolver(PUBLISHED_OK)
    facts = _collect(responses, resolver)
    initial = next(d for d in facts["verified_domains"] if d["id"] == "acme.onmicrosoft.com")
    assert initial["is_initial"] is True
    assert "spf_present" not in initial and "dns_unavailable" not in initial
    assert not any("onmicrosoft" in name for name, _ in resolver.queries)


def test_published_spf_dmarc_dkim_are_read_from_dns():
    responses = _baseline(
        domain_rows=[{"id": "acme.com", "isVerified": True, "isInitial": False}],
        domain_dns={}, user_rows=[], user_mailbox={},
    )
    resolver = FakeResolver(PUBLISHED_OK)
    d = _collect(responses, resolver)["verified_domains"][0]
    assert d["spf_present"] is True
    assert d["dmarc_present"] is True
    assert d["dkim_present"] is True
    assert d["dns_source"] == "published_dns"
    assert ("acme.com", "TXT") in resolver.queries
    assert ("_dmarc.acme.com", "TXT") in resolver.queries
    assert ("selector2._domainkey.acme.com", "CNAME") in resolver.queries


def test_nothing_published_is_a_definite_absence():
    """NXDOMAIN / no answer is a finding, not a gap: this used to pass 2.1.8
    because Microsoft's *required* records always contain the SPF TXT."""
    responses = _baseline(
        domain_rows=[{"id": "acme.com", "isVerified": True, "isInitial": False}],
        domain_dns={}, user_rows=[], user_mailbox={},
    )
    d = _collect(responses, FakeResolver({}))["verified_domains"][0]
    assert d["spf_present"] is False
    assert d["dmarc_present"] is False
    assert d["dkim_present"] is False


def test_a_txt_that_is_not_spf_does_not_count():
    responses = _baseline(
        domain_rows=[{"id": "acme.com", "isVerified": True, "isInitial": False}],
        domain_dns={}, user_rows=[], user_mailbox={},
    )
    resolver = FakeResolver({("acme.com", "TXT"): ["MS=ms12345678"],
                             ("_dmarc.acme.com", "TXT"): ["v=spf1 -all"]})
    d = _collect(responses, resolver)["verified_domains"][0]
    assert d["spf_present"] is False
    assert d["dmarc_present"] is False


def test_service_configuration_records_are_not_read():
    """The wrong source must not be consulted at all."""
    responses = _baseline(
        domain_rows=[{"id": "acme.com", "isVerified": True, "isInitial": False}],
        domain_dns={}, user_rows=[], user_mailbox={},
    )
    raises = {"/domains/acme.com/serviceConfigurationRecords"}
    d = _collect(responses, FakeResolver(PUBLISHED_OK), raises=raises)["verified_domains"][0]
    assert d["spf_present"] is True


def test_dns_lookup_failure_marks_domain_unavailable_not_false():
    # A domain whose records could not be READ is dns_unavailable -- NOT
    # spf/dkim/dmarc=false, which defender_validation.rego would read as a
    # definite violation, and never true.
    responses = _baseline(
        domain_rows=[{"id": "acme.com", "isVerified": True, "isInitial": False}],
        domain_dns={}, user_rows=[], user_mailbox={},
    )
    d = _collect(responses, FakeResolver(PUBLISHED_OK, failing={"_dmarc.acme.com"}))["verified_domains"][0]
    assert d["dns_unavailable"].startswith("evidence missing:")
    assert "timed out" in d["dns_unavailable"]
    assert "spf_present" not in d
    assert "dkim_present" not in d
    assert "dmarc_present" not in d


def test_no_dns_library_is_evidence_missing_for_every_customer_domain():
    responses = _baseline(
        domain_rows=[
            {"id": "acme.onmicrosoft.com", "isVerified": True, "isInitial": True},
            {"id": "acme.com", "isVerified": True, "isInitial": False},
            {"id": "acme.net", "isVerified": True, "isInitial": False},
        ],
        domain_dns={}, user_rows=[], user_mailbox={},
    )
    facts = _collect(responses, resolver=None)   # no resolver -> library missing
    custom = [d for d in facts["verified_domains"] if not d["is_initial"]]
    assert len(custom) == 2
    for d in custom:
        assert d["dns_unavailable"] == m365_exchange_facts.DNS_LIBRARY_MISSING
        assert "spf_present" not in d


def test_legacy_record_classifier_still_classifies():
    """_classify_dns_records is no longer on the verdict path; its parsing
    is still pinned so nobody reuses it wrongly."""
    out = m365_exchange_facts._classify_dns_records([
        {"recordType": "TXT", "label": "@", "text": "v=spf1 -all"},
        {"recordType": "TXT", "label": "_dmarc", "text": "v=DMARC1; p=reject"},
        {"recordType": "CNAME", "label": "selector1._domainkey", "text": "x"},
    ])
    assert out == {"spf_present": True, "dmarc_present": True, "dkim_present": True}


# ── Mailbox audit aggregate ─────────────────────────────────────────


def test_mailbox_audit_summary_counts_enabled_and_disabled():
    responses = _baseline(
        domain_rows=[],
        domain_dns={},
        user_rows=[
            {"id": "u-1", "userPrincipalName": "alice@example.com"},
            {"id": "u-2", "userPrincipalName": "bob@example.com"},
            {"id": "u-3", "userPrincipalName": "carol@example.com"},
        ],
        user_mailbox={
            "u-1": {"mailboxAuditEnabled": True},
            "u-2": {"mailboxAuditEnabled": False},
            "u-3": {"mailboxAuditEnabled": True},
        },
    )
    facts = m365_exchange_facts.collect_facts(FakeGraphClient(responses))
    s = facts["mailbox_audit_summary"]
    assert s["audit_enabled"] == 2
    assert s["audit_disabled"] == 1
    assert s["sampled"] == 3
    assert s["evaluable"] is True


def test_mailbox_audit_evaluable_false_when_no_key_present():
    """If the mailboxAuditEnabled key isn't surfaced by Graph for
    any user, mark the result not-evaluable so Rego can emit the
    right message."""
    responses = _baseline(
        domain_rows=[],
        domain_dns={},
        user_rows=[
            {"id": "u-1", "userPrincipalName": "alice@example.com"},
        ],
        user_mailbox={
            "u-1": {"archiveFolder": "Archive"},     # no audit key
        },
    )
    facts = m365_exchange_facts.collect_facts(FakeGraphClient(responses))
    s = facts["mailbox_audit_summary"]
    assert s["evaluable"] is False
    assert s["sampled"] == 1


def test_user_without_exchange_license_is_skipped():
    """A user whose mailboxSettings returns 403/404 just gets
    skipped — the assessment continues for everyone else."""
    responses = _baseline(
        domain_rows=[],
        domain_dns={},
        user_rows=[
            {"id": "u-1", "userPrincipalName": "alice@example.com"},
            {"id": "u-2", "userPrincipalName": "bob@example.com"},
        ],
        user_mailbox={
            "u-1": {"mailboxAuditEnabled": True},
            # u-2 has no mailboxSettings entry — Graph 403
        },
    )
    raises = {"/users/u-2/mailboxSettings"}
    facts = m365_exchange_facts.collect_facts(FakeGraphClient(responses, raises=raises))
    assert facts["mailbox_audit_summary"]["sampled"] == 1
    assert facts["mailbox_audit_summary"]["audit_enabled"] == 1


# ── Secure Score projection ─────────────────────────────────────────


def test_secure_score_projects_only_relevant_controls():
    responses = _baseline(
        domain_rows=[],
        domain_dns={},
        user_rows=[],
        user_mailbox={},
    )
    for row in (
        {"id": "MFARegistrationV2", "title": "MFA reg", "implementationStatus": "Implemented"},
        {"id": "SMTPAuthDisabled", "title": "SMTP AUTH disabled", "implementationStatus": "Implemented"},
        {"id": "ExternalSenderTagging", "title": "Ext tag", "implementationStatus": "NotImplemented"},
        {"id": "SomethingUnrelated", "title": "noise", "implementationStatus": "Implemented"},
    ):
        responses[f"/security/secureScoreControlProfiles/{row['id']}"] = row
    facts = m365_exchange_facts.collect_facts(FakeGraphClient(responses))
    ids = {c["id"] for c in facts["secure_score_controls"]}
    assert ids == {"MFARegistrationV2", "SMTPAuthDisabled", "ExternalSenderTagging"}
    assert "SomethingUnrelated" not in ids
