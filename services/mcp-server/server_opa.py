"""
AAP MCP Server with OPA Governance
Three-layer enforcement:
  1. Tool list filtering   — blocked tools never appear in the agent's catalog
  2. Call-time OPA check   — every tool call validated before execution
  3. Persisted decision log — every verdict (allow AND deny) written append-only
     to the compliance DB (ai_action_log), keyed by trace_id and agent identity

Uses ansible_mcp_tools natively (no FastAPI dependency).
"""
import hashlib
import json
import uuid
from os import environ
from typing import Any, Sequence

import httpx
from mcp.server.fastmcp.utilities.logging import get_logger, configure_logging
from mcp.types import TextContent, ImageContent, EmbeddedResource

from ansible_mcp_tools.registry import register_service_url, init as init_registry
from ansible_mcp_tools.server import LightspeedOpenAPIAAPServer
from ansible_mcp_tools.openapi.spec_loaders import FileLoader
from ansible_mcp_tools.openapi.tool_rules import (
    NoDescriptionRule,
    AllowOnlyMethodsRule,
    OperationIdBlackRule,
)
from ansible_mcp_tools.authentication import LightspeedAuthenticationBackend
from ansible_mcp_tools.authentication.validators.aap_token_validator import AAPTokenValidator
from ansible_mcp_tools.authentication.validators.aap_jwt_validator import AAPJWTValidator

logger = get_logger(__name__)
configure_logging("WARNING")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
AAP_GATEWAY_URL = environ.get("AAP_GATEWAY_URL")
AAP_SERVICE_URL = environ.get("AAP_SERVICE_URL")
URL = environ.get("CONTROLLER_OPENAPI_SPEC_URL")
HOST = environ.get("HOST", "0.0.0.0")
PORT = int(environ.get("PORT", 8004))
OPA_URL = environ.get("OPA_URL", "http://host.containers.internal:8182")
OPA_PATH = "/v1/data/ai_governance/mcp/response"
# Governance is UNCONDITIONAL. There is no disable path: the customer-facing
# claim is "every tool call passes through the policy engine", and a
# configuration knob that unforces it makes that claim false (flagged by
# review as a fail-open bypass). An attempt to configure the old flag off
# refuses to start rather than silently starting ungoverned.
if environ.get("OPA_GOVERNANCE_ENABLED", "true").lower() == "false":
    raise SystemExit(
        "OPA_GOVERNANCE_ENABLED=false is not supported: governance is "
        "unconditional. For development, point OPA_URL at a permissive local "
        "OPA — do not run this server ungoverned."
    )

# Agent identity sent to OPA and written to the decision log. One deployed
# server instance serves one agent identity (deployments are per-agent); the
# per-request authenticated principal is not exposed by ansible_mcp_tools'
# call_tool signature, so identity binds at deployment scope.
# Empty/whitespace env value degrades to "unregistered", never "" — a blank
# identity must not accidentally match a registry entry or log as anonymous.
AGENT_ID = environ.get("MCP_AGENT_ID", "").strip() or "unregistered"

# Decision log: DSN for the compliance DB. Empty → logging disabled (decision
# still enforced, but unevidenced — deployment should always set this).
# DECISION_LOG_REQUIRED=true → a failed log write turns the call into a
# refusal: no evidence, no action (the crown-jewels posture).
DECISION_LOG_DSN = environ.get("DECISION_LOG_DSN", "")
DECISION_LOG_REQUIRED = environ.get("DECISION_LOG_REQUIRED", "false").lower() == "true"

try:
    import psycopg
except ImportError:  # image not yet rebuilt with psycopg — logging unavailable
    psycopg = None


def _log_decision(trace_id: str, tool: str, arguments: dict, result: dict) -> bool:
    """Persist one verdict to ai_action_log. Returns True on success."""
    if not DECISION_LOG_DSN:
        return False
    if psycopg is None:
        logger.error("decision log configured but psycopg is not installed")
        return False
    args_hash = hashlib.sha256(
        json.dumps(arguments, sort_keys=True, default=str).encode()
    ).hexdigest()
    try:
        with psycopg.connect(DECISION_LOG_DSN, connect_timeout=3) as conn:
            conn.execute(
                """
                INSERT INTO ai_action_log
                    (trace_id, channel, agent_identity, tool, arguments_hash,
                     risk_level, decision, allow, reason)
                VALUES (%s, 'mcp', %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    trace_id,
                    AGENT_ID,
                    tool,
                    args_hash,
                    result.get("risk_level", "unknown"),
                    result.get("decision", "DENY"),
                    bool(result.get("allow", False)),
                    result.get("reason", ""),
                ),
            )
        return True
    except Exception as e:
        logger.error(f"decision log write failed trace={trace_id}: {e}")
        return False

# ---------------------------------------------------------------------------
# Layer 1: Tool list rules (applied at startup — blocked tools never visible)
# ---------------------------------------------------------------------------
# Block all destructive and privileged POST operations
BLOCKED_OPERATIONS = [
    # Credential management
    "api_credentials_create", "api_credentials_update", "api_credentials_partial_update",
    "api_credentials_test_create",
    # User/org admin
    "api_users_create", "api_users_update", "api_users_partial_update",
    "api_organizations_create", "api_organizations_update", "api_organizations_partial_update",
    "api_organizations_admins_create",
    # System settings
    "api_settings_update", "api_settings_partial_update",
    "api_config_create",
    # Job cancellation
    "api_jobs_cancel_create",
    "api_workflow_jobs_cancel_create",
    # Execution environment admin
    "api_execution_environments_create", "api_execution_environments_update",
    "api_execution_environments_partial_update",
    # Team admin
    "api_teams_create", "api_teams_update", "api_teams_partial_update",
]

# ---------------------------------------------------------------------------
# Layer 2: OPA call-time enforcement
# ---------------------------------------------------------------------------
def _opa_check(tool_name: str, arguments: dict) -> dict:
    """Query OPA. Raises RuntimeError on unreachable (fail-closed)."""
    payload = {"input": {"tool": tool_name, "arguments": arguments, "agent": AGENT_ID}}
    try:
        r = httpx.post(f"{OPA_URL}{OPA_PATH}", json=payload, timeout=5.0, verify=False)
        r.raise_for_status()
        return r.json().get("result", {})
    except httpx.TimeoutException:
        raise RuntimeError(f"OPA timeout for '{tool_name}' — failing closed")
    except Exception as e:
        raise RuntimeError(f"OPA unreachable for '{tool_name}': {e} — failing closed")


# ---------------------------------------------------------------------------
# Governed MCP server — subclasses call_tool to add OPA enforcement
# ---------------------------------------------------------------------------
class OPAGovernedAAPServer(LightspeedOpenAPIAAPServer):

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> Sequence[TextContent | ImageContent | EmbeddedResource]:

        trace_id = str(uuid.uuid4())
        try:
            result = _opa_check(name, arguments)
        except RuntimeError as e:
            logger.error(f"trace={trace_id} {e}")
            _log_decision(trace_id, name, arguments, {
                "decision": "DENY", "allow": False,
                "risk_level": "unknown", "reason": f"fail-closed: {e}",
            })
            return [TextContent(type="text", text=f"OPA ERROR [trace {trace_id}]: {e}")]

        decision = result.get("decision", "DENY")
        reason = result.get("reason", "No reason provided")
        risk = result.get("risk_level", "unknown")

        logged = _log_decision(trace_id, name, arguments, result)
        logger.warning(
            f"OPA [{decision}] tool={name} agent={AGENT_ID} risk={risk} "
            f"trace={trace_id} logged={logged}"
        )

        if DECISION_LOG_REQUIRED and not logged:
            return [TextContent(
                type="text",
                text=f"GOVERNANCE ERROR [trace {trace_id}]: decision log unavailable "
                     f"and DECISION_LOG_REQUIRED is set — no evidence, no action."
            )]

        if not result.get("allow", False):
            return [TextContent(
                type="text",
                text=f"OPA DENY [{risk}] [trace {trace_id}]: {reason}\n"
                     f"Tool '{name}' is not permitted for AI agents."
            )]


        logger.warning(f"--> Tool call {name}, {arguments}")
        return await self._tool_caller.tool_call(name, arguments)


# ---------------------------------------------------------------------------
# Server startup
# ---------------------------------------------------------------------------
init_registry()
register_service_url("gateway", AAP_GATEWAY_URL)
register_service_url("controller", AAP_SERVICE_URL)

logger.warning("OPA governance: UNCONDITIONAL (no disable path)")
logger.warning(f"OPA endpoint: {OPA_URL}{OPA_PATH}")
logger.warning(f"Agent identity: {AGENT_ID}")
logger.warning(
    "Decision log: "
    + ("ENABLED" if DECISION_LOG_DSN else "DISABLED (set DECISION_LOG_DSN)")
    + (" [REQUIRED]" if DECISION_LOG_REQUIRED else "")
)
logger.warning(f"Blocked operations: {len(BLOCKED_OPERATIONS)} operations removed from tool list")

mcp = OPAGovernedAAPServer(
    name="AAP Controller API — OPA Governed MCP Server",
    service_name="controller",
    auth_backend=LightspeedAuthenticationBackend(
        authentication_validators=[
            AAPJWTValidator(AAP_GATEWAY_URL, verify_cert=False),
            AAPTokenValidator(AAP_GATEWAY_URL, verify_cert=False),
        ]
    ),
    spec_loader=FileLoader(URL),
    tool_rules=[
        NoDescriptionRule(),
        AllowOnlyMethodsRule(["get", "post"]),   # Block DELETE, PUT, PATCH entirely
        OperationIdBlackRule(BLOCKED_OPERATIONS), # Block dangerous POST operations
    ],
    host=HOST,
    port=PORT,
)

if __name__ == "__main__":
    # streamable-http serves /mcp — matches the role defaults and README.
    mcp.run(transport=environ.get("MCP_TRANSPORT", "streamable-http"))
