"""Bridge the ansible_collections.* import namespace for pytest.

Ansible's collection loader handles the
`ansible_collections.<namespace>.<name>.*` import path at runtime
(it's a custom finder/loader machinery). When you run unit tests
under plain pytest (not `ansible-test`), that machinery isn't
active and `from ansible_collections.aac.m365... import ...`
raises ModuleNotFoundError.

This conftest pre-populates sys.modules so the canonical import
path resolves to the actual files on disk. Result: tests can
import the module under its real name without depending on
ansible-test.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


COLLECTION_ROOT = Path(__file__).resolve().parents[2]


def _ensure_namespace(name: str) -> None:
    """Create the parent namespace modules so `from X.Y import Z`
    can walk the chain without erroring on a missing intermediate."""
    if name in sys.modules:
        return
    sys.modules[name] = types.ModuleType(name)


def _register_file(qualified_name: str, file_path: Path) -> None:
    """Load a file and register it under `qualified_name`."""
    spec = importlib.util.spec_from_file_location(qualified_name, str(file_path))
    assert spec and spec.loader, f"could not build spec for {file_path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[qualified_name] = mod
    spec.loader.exec_module(mod)


# Stub ansible.module_utils.basic so the module under test can be
# imported without ansible-core installed. Tests exercise pure
# functions (`collect_facts`) directly, not `main()`, so the stub
# only needs to satisfy the import.
if "ansible.module_utils.basic" not in sys.modules:
    sys.modules["ansible"] = types.ModuleType("ansible")
    sys.modules["ansible.module_utils"] = types.ModuleType("ansible.module_utils")
    _basic = types.ModuleType("ansible.module_utils.basic")

    class _StubAnsibleModule:
        def __init__(self, **kwargs):
            self.params: dict = {}
            self.check_mode = False

        def exit_json(self, **kwargs):
            raise SystemExit(0)

        def fail_json(self, **kwargs):
            raise SystemExit(1)

    _basic.AnsibleModule = _StubAnsibleModule
    sys.modules["ansible.module_utils.basic"] = _basic


# Namespace parents.
for ns in (
    "ansible_collections",
    "ansible_collections.aac",
    "ansible_collections.aac.m365",
    "ansible_collections.aac.m365.plugins",
    "ansible_collections.aac.m365.plugins.module_utils",
    "ansible_collections.aac.m365.plugins.modules",
):
    _ensure_namespace(ns)

# The actual modules we need to make importable. Adding more files
# here is mechanical — match the qualified name to the on-disk
# file path.
_register_file(
    "ansible_collections.aac.m365.plugins.module_utils.graph",
    COLLECTION_ROOT / "plugins" / "module_utils" / "graph.py",
)
_register_file(
    "ansible_collections.aac.m365.plugins.module_utils.pwsh",
    COLLECTION_ROOT / "plugins" / "module_utils" / "pwsh.py",
)
_register_file(
    "ansible_collections.aac.m365.plugins.modules.m365_identity_facts",
    COLLECTION_ROOT / "plugins" / "modules" / "m365_identity_facts.py",
)
# The collectors carrying the six controls that closed the 2026-08-25
# coverage gap. pwsh must be registered above these -- the PowerShell
# collectors import it at module scope.
_register_file(
    "ansible_collections.aac.m365.plugins.modules.m365_admin_center_facts",
    COLLECTION_ROOT / "plugins" / "modules" / "m365_admin_center_facts.py",
)
_register_file(
    "ansible_collections.aac.m365.plugins.modules.m365_entra_facts",
    COLLECTION_ROOT / "plugins" / "modules" / "m365_entra_facts.py",
)
_register_file(
    "ansible_collections.aac.m365.plugins.modules.m365_exchange_ps_facts",
    COLLECTION_ROOT / "plugins" / "modules" / "m365_exchange_ps_facts.py",
)
_register_file(
    "ansible_collections.aac.m365.plugins.modules.m365_defender_ps_facts",
    COLLECTION_ROOT / "plugins" / "modules" / "m365_defender_ps_facts.py",
)
_register_file(
    "ansible_collections.aac.m365.plugins.modules.m365_exchange_facts",
    COLLECTION_ROOT / "plugins" / "modules" / "m365_exchange_facts.py",
)
_register_file(
    "ansible_collections.aac.m365.plugins.modules.m365_defender_facts",
    COLLECTION_ROOT / "plugins" / "modules" / "m365_defender_facts.py",
)
_register_file(
    "ansible_collections.aac.m365.plugins.modules.m365_purview_facts",
    COLLECTION_ROOT / "plugins" / "modules" / "m365_purview_facts.py",
)
_register_file(
    "ansible_collections.aac.m365.plugins.modules.m365_fabric_facts",
    COLLECTION_ROOT / "plugins" / "modules" / "m365_fabric_facts.py",
)
_register_file(
    "ansible_collections.aac.m365.plugins.modules.m365_sharepoint_facts",
    COLLECTION_ROOT / "plugins" / "modules" / "m365_sharepoint_facts.py",
)
_register_file(
    "ansible_collections.aac.m365.plugins.modules.m365_teams_facts",
    COLLECTION_ROOT / "plugins" / "modules" / "m365_teams_facts.py",
)
