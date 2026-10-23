#!/usr/bin/env python3
"""Verify a portal-signed bundle envelope (ed25519 JWS-style).

Envelope contract (AAC_Customer_Portal api/src/core/bundle_signer.py):

    {
      "v": 1, "alg": "ed25519", "key_id": "<rotation-key-id>",
      "payload": { "tenant_id": ..., "bundle_sha256": ..., ... },
      "signature": "<base64(ed25519(canonical_payload_json))>"
    }

The signature covers the CANONICAL payload — json.dumps with
sort_keys=True and (",", ":") separators — so this verifier
re-canonicalises before checking; any in-flight reformatting of the
envelope therefore fails verification instead of passing silently.

Uses `cryptography` (a hard dependency of ansible-core, so present in
every execution environment that can run this role).

Exit 0: verified — canonical payload JSON printed to stdout.
Exit 1: verification failed — reason on stderr, nothing on stdout.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from typing import NoReturn

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def fail(reason: str) -> NoReturn:
    print(f"envelope verification FAILED: {reason}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--envelope", required=True, help="path to the envelope JSON file")
    ap.add_argument("--public-key-b64", required=True, help="portal ed25519 public key, base64")
    ap.add_argument("--expected-key-id", default="", help="fail unless envelope key_id matches")
    args = ap.parse_args()

    try:
        with open(args.envelope, "r", encoding="utf-8") as fh:
            env = json.load(fh)
    except (OSError, ValueError) as exc:
        fail(f"cannot read envelope: {exc}")

    if env.get("v") != 1:
        fail(f"unsupported envelope version: {env.get('v')!r}")
    if env.get("alg") != "ed25519":
        fail(f"unsupported alg: {env.get('alg')!r}")
    if args.expected_key_id and env.get("key_id") != args.expected_key_id:
        fail(
            f"key_id mismatch: envelope={env.get('key_id')!r} "
            f"expected={args.expected_key_id!r}"
        )

    payload = env.get("payload")
    if not isinstance(payload, dict):
        fail("envelope payload missing or not an object")
    if not payload.get("bundle_sha256"):
        fail("payload has no bundle_sha256")

    try:
        pub = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(args.public_key_b64, validate=True)
        )
        signature = base64.b64decode(env["signature"], validate=True)
    except Exception as exc:  # noqa: BLE001 - any decode error is a verify failure
        fail(f"cannot decode key/signature: {exc}")

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    try:
        pub.verify(signature, canonical)
    except InvalidSignature:
        fail("ed25519 signature does not match canonical payload")

    # Verified — emit the canonical payload for the caller to consume.
    print(canonical.decode("utf-8"))


if __name__ == "__main__":
    main()
