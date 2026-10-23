#!/usr/bin/env python3
"""CLI tests for files/verify_envelope.py — the trust boundary.

Exercises the ACTUAL production entry point via subprocess (not a
reimplementation): valid envelope, tampered payload, tampered
signature, malformed JSON, key-id mismatch, wrong public key.

Run directly (no pytest needed — exits non-zero on any failure):

    python3 ansible/roles/aac_bundle_consumer/tests/test_verify_envelope.py

Also collectable by pytest if a runner is ever wired into CI.
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

VERIFIER = str(Path(__file__).resolve().parent.parent / "files" / "verify_envelope.py")

_key = Ed25519PrivateKey.generate()
_pub_b64 = base64.b64encode(
    _key.public_key().public_bytes_raw()
).decode()

PAYLOAD = {
    "tenant_id": "33333333-3333-3333-3333-333333333333",
    "bundle_sha256": "ab" * 32,
    "bundle_byte_size": 4,
    "target_count": 1,
    "customer_policy_ids": [],
    "signed_at": "2026-09-23T00:00:00+00:00",
}


def _envelope(payload: dict, *, key_id: str = "test-key", garble_sig: bool = False) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    sig = _key.sign(canonical)
    if garble_sig:
        sig = bytes([sig[0] ^ 0xFF]) + sig[1:]
    return json.dumps(
        {
            "v": 1,
            "alg": "ed25519",
            "key_id": key_id,
            "payload": payload,
            "signature": base64.b64encode(sig).decode(),
        }
    )


def _run(envelope_text: str, *extra: str, pub: str = _pub_b64) -> subprocess.CompletedProcess:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        fh.write(envelope_text)
        path = fh.name
    return subprocess.run(
        [sys.executable, VERIFIER, "--envelope", path, "--public-key-b64", pub, *extra],
        capture_output=True,
        text=True,
    )


def test_valid_envelope_verifies_and_emits_canonical_payload():
    r = _run(_envelope(PAYLOAD))
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == PAYLOAD


def test_tampered_payload_rejected():
    env = json.loads(_envelope(PAYLOAD))
    env["payload"]["bundle_sha256"] = "cd" * 32
    r = _run(json.dumps(env))
    assert r.returncode == 1
    assert "signature does not match" in r.stderr
    assert r.stdout == ""


def test_tampered_signature_rejected():
    r = _run(_envelope(PAYLOAD, garble_sig=True))
    assert r.returncode == 1
    assert r.stdout == ""


def test_malformed_json_rejected():
    r = _run("this is not json {")
    assert r.returncode == 1
    assert "cannot read envelope" in r.stderr


def test_key_id_mismatch_rejected():
    r = _run(_envelope(PAYLOAD, key_id="rotated-key"), "--expected-key-id", "test-key")
    assert r.returncode == 1
    assert "key_id mismatch" in r.stderr


def test_wrong_public_key_rejected():
    other = Ed25519PrivateKey.generate()
    other_pub = base64.b64encode(other.public_key().public_bytes_raw()).decode()
    r = _run(_envelope(PAYLOAD), pub=other_pub)
    assert r.returncode == 1


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if failures else 0)
