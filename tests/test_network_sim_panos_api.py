"""The network simulator answers the PAN-OS XML API requests the CIS collector sends."""
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "network_sim", os.path.join(ROOT, "examples/simulators/network/network_sim.py"))
sim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sim)

SHOW_CONFIG = "<show><config><running></running></config></show>"


def test_a_request_without_a_key_is_refused():
    status, body = sim.panos_api({"type": "op", "cmd": SHOW_CONFIG}, "")
    assert status == 403 and 'status="error"' in body


def test_a_fixed_key_is_enforced_when_set(monkeypatch):
    monkeypatch.setenv("PANOS_SIM_API_KEY", "expected")
    assert sim.panos_api({"type": "op", "cmd": SHOW_CONFIG}, "other")[0] == 403
    assert sim.panos_api({"type": "op", "cmd": SHOW_CONFIG}, "expected")[0] == 200


def test_the_three_commands_the_collector_sends():
    status, body = sim.panos_api({"type": "op", "cmd": SHOW_CONFIG}, "k")
    assert status == 200 and 'status="success"' in body and "<config" in body
    status, body = sim.panos_api({"type": "op", "cmd": "<request><license><info></info></license></request>"}, "k")
    assert status == 200 and "<licenses>" in body
    status, body = sim.panos_api({"type": "op", "cmd": "<show><system><info></info></system></show>"}, "k")
    assert status == 200 and "<sw-version>" in body


def test_anything_else_is_an_error():
    assert sim.panos_api({"type": "config", "action": "set"}, "k")[0] == 400
    assert sim.panos_api({"type": "op", "cmd": "<request><restart><system/></restart></request>"}, "k")[0] == 400
