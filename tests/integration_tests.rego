package tests.integration

import rego.v1

# ---------------------------------------------------------------------------
# Integration tests — end-to-end checks that exercise multiple policy modules
# together and validate the aggregated compliance_report output shape.
#
# These tests validate cross-module interactions (e.g., that an orchestrator
# correctly aggregates violations from all sub-modules).
#
# Grow this file by adding test_ functions that use real-shaped input data.
# ---------------------------------------------------------------------------

# Placeholder — always passes; ensures CI matrix has a real file to execute.
test_placeholder if { true }
