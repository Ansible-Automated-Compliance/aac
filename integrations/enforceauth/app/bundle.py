"""Build an OPA bundle (gzipped tar) carrying AAC compliance state as `data`.

EnforceAuth's Writ control plane "ships bundles" to edge-deployed OPA runtimes
(sidecar / gateway / in-app), including air-gapped. Serving compliance state as a
bundle lets Herald "compose Writ data with your own" without a per-decision
network hop — the edge OPA pulls this bundle periodically and exposes it at
`data.aac.compliance.hosts.<hostname>`.

Bundle layout (OPA spec):
    /data.json    -> {"aac": {"compliance": {...}}}
    /.manifest    -> {"roots": ["aac/compliance"], "revision": "<ts>"}
"""
from __future__ import annotations

import gzip
import io
import json
import tarfile
import time


def build_bundle(compliance: dict, revision: str | None = None) -> bytes:
    """Return gzipped-tar bundle bytes. `compliance` is placed at data.aac.compliance."""
    data = {"aac": {"compliance": compliance}}
    manifest = {"roots": ["aac/compliance"], "revision": revision or str(int(time.time()))}

    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for name, obj in (("/data.json", data), ("/.manifest", manifest)):
            payload = json.dumps(obj).encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))

    return gzip.compress(raw.getvalue())
