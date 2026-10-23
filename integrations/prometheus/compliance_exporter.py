"""
AAC Compliance Prometheus Exporter
Reads latest compliance results from PostgreSQL and exposes them as Prometheus metrics.

Metrics exposed on :9101/metrics:
  aac_compliance_score        — compliance percentage (latest per hostname+framework)
  aac_compliant               — 1=compliant 0=non-compliant (latest per hostname+framework)
  aac_controls_total          — total controls evaluated (latest per hostname+framework)
  aac_controls_passed         — passing controls (latest per hostname+framework)
  aac_controls_failed         — failing controls (latest per hostname+framework)
  aac_violations_total        — number of violations (latest per hostname+framework)
  aac_assessments_24h         — assessments run in the last 24 hours (per framework)
  aac_last_assessment_seconds — Unix timestamp of most recent assessment per hostname+framework

Environment variables:
  POSTGRES_HOST     — default: localhost
  POSTGRES_PORT     — default: 5432
  POSTGRES_DB       — default: compliance
  POSTGRES_USER     — default: compliance_reader
  POSTGRES_PASSWORD — required
  EXPORTER_PORT     — default: 9101
  SCRAPE_INTERVAL   — default: 60 (seconds between DB refresh)
"""

import os
import time
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import psycopg2
import psycopg2.extras

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
POSTGRES_HOST     = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT     = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB       = os.getenv("POSTGRES_DB", "compliance")
POSTGRES_USER     = os.getenv("POSTGRES_USER", "compliance_reader")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
EXPORTER_PORT     = int(os.getenv("EXPORTER_PORT", "9101"))
SCRAPE_INTERVAL   = int(os.getenv("SCRAPE_INTERVAL", "60"))

# ---------------------------------------------------------------------------
# Metric cache (refreshed in background thread)
# ---------------------------------------------------------------------------
_metrics_cache = ""
_cache_lock = threading.Lock()


def _connect():
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        connect_timeout=10,
    )


def _escape_label(value: str) -> str:
    """Escape double-quotes and backslashes in Prometheus label values."""
    if value is None:
        return "unknown"
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _build_metrics() -> str:
    """Query PostgreSQL and build the full Prometheus exposition text."""
    try:
        with _connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:

                # ── Latest result per (hostname, framework) ──────────────────
                cur.execute("""
                    SELECT DISTINCT ON (hostname, framework)
                        hostname,
                        framework,
                        compliance_percentage,
                        compliant,
                        total_controls,
                        passed_controls,
                        failed_controls,
                        violations,
                        evaluation_timestamp
                    FROM compliance_results
                    WHERE hostname IS NOT NULL
                      AND framework IS NOT NULL
                    ORDER BY hostname, framework, evaluation_timestamp DESC
                """)
                latest_rows = cur.fetchall()

                # ── Assessment counts for last 24h per framework ──────────────
                cur.execute("""
                    SELECT framework, COUNT(*) AS cnt
                    FROM compliance_results
                    WHERE evaluation_timestamp > NOW() - INTERVAL '24 hours'
                      AND framework IS NOT NULL
                    GROUP BY framework
                """)
                assessment_24h = {row["framework"]: row["cnt"] for row in cur.fetchall()}

    except Exception as e:
        logger.error(f"DB query failed: {e}")
        return f"# ERROR fetching metrics: {e}\n"

    lines = []

    # ── aac_compliance_score ──────────────────────────────────────────────────
    lines.append("# HELP aac_compliance_score Compliance percentage (0-100) from latest assessment")
    lines.append("# TYPE aac_compliance_score gauge")
    for row in latest_rows:
        host = _escape_label(row["hostname"])
        fw   = _escape_label(row["framework"])
        val  = float(row["compliance_percentage"]) if row["compliance_percentage"] is not None else 0.0
        lines.append(f'aac_compliance_score{{hostname="{host}",framework="{fw}"}} {val:.2f}')

    # ── aac_compliant ─────────────────────────────────────────────────────────
    lines.append("# HELP aac_compliant 1 if fully compliant, 0 if not (latest assessment)")
    lines.append("# TYPE aac_compliant gauge")
    for row in latest_rows:
        host = _escape_label(row["hostname"])
        fw   = _escape_label(row["framework"])
        val  = 1 if row["compliant"] else 0
        lines.append(f'aac_compliant{{hostname="{host}",framework="{fw}"}} {val}')

    # ── aac_controls_total ────────────────────────────────────────────────────
    lines.append("# HELP aac_controls_total Total controls evaluated in latest assessment")
    lines.append("# TYPE aac_controls_total gauge")
    for row in latest_rows:
        host = _escape_label(row["hostname"])
        fw   = _escape_label(row["framework"])
        val  = int(row["total_controls"]) if row["total_controls"] is not None else 0
        lines.append(f'aac_controls_total{{hostname="{host}",framework="{fw}"}} {val}')

    # ── aac_controls_passed ───────────────────────────────────────────────────
    lines.append("# HELP aac_controls_passed Passing controls in latest assessment")
    lines.append("# TYPE aac_controls_passed gauge")
    for row in latest_rows:
        host = _escape_label(row["hostname"])
        fw   = _escape_label(row["framework"])
        val  = int(row["passed_controls"]) if row["passed_controls"] is not None else 0
        lines.append(f'aac_controls_passed{{hostname="{host}",framework="{fw}"}} {val}')

    # ── aac_controls_failed ───────────────────────────────────────────────────
    lines.append("# HELP aac_controls_failed Failing controls in latest assessment")
    lines.append("# TYPE aac_controls_failed gauge")
    for row in latest_rows:
        host = _escape_label(row["hostname"])
        fw   = _escape_label(row["framework"])
        val  = int(row["failed_controls"]) if row["failed_controls"] is not None else 0
        lines.append(f'aac_controls_failed{{hostname="{host}",framework="{fw}"}} {val}')

    # ── aac_violations_total ──────────────────────────────────────────────────
    lines.append("# HELP aac_violations_total Number of violations in latest assessment")
    lines.append("# TYPE aac_violations_total gauge")
    for row in latest_rows:
        host = _escape_label(row["hostname"])
        fw   = _escape_label(row["framework"])
        violations = row["violations"]
        if violations is None:
            count = 0
        elif isinstance(violations, list):
            count = len(violations)
        elif isinstance(violations, dict):
            count = len(violations.get("violations", violations))
        else:
            count = 0
        lines.append(f'aac_violations_total{{hostname="{host}",framework="{fw}"}} {count}')

    # ── aac_last_assessment_seconds ───────────────────────────────────────────
    lines.append("# HELP aac_last_assessment_seconds Unix timestamp of most recent assessment")
    lines.append("# TYPE aac_last_assessment_seconds gauge")
    for row in latest_rows:
        host = _escape_label(row["hostname"])
        fw   = _escape_label(row["framework"])
        ts   = row["evaluation_timestamp"]
        val  = ts.timestamp() if ts else 0
        lines.append(f'aac_last_assessment_seconds{{hostname="{host}",framework="{fw}"}} {val:.0f}')

    # ── aac_assessments_24h ───────────────────────────────────────────────────
    lines.append("# HELP aac_assessments_24h Assessments completed in the last 24 hours")
    lines.append("# TYPE aac_assessments_24h gauge")
    for fw, cnt in assessment_24h.items():
        fw_label = _escape_label(fw)
        lines.append(f'aac_assessments_24h{{framework="{fw_label}"}} {cnt}')

    return "\n".join(lines) + "\n"


def _refresh_loop():
    """Background thread: refresh metric cache every SCRAPE_INTERVAL seconds."""
    while True:
        logger.info("Refreshing compliance metrics from PostgreSQL…")
        fresh = _build_metrics()
        with _cache_lock:
            global _metrics_cache
            _metrics_cache = fresh
        logger.info(f"Metrics refreshed — {len(fresh.splitlines())} lines")
        time.sleep(SCRAPE_INTERVAL)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/metrics", "/metrics/"):
            with _cache_lock:
                body = _metrics_cache.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path in ("/health", "/healthz"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"healthy","service":"aac-compliance-exporter"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        # Suppress default access logging to reduce noise
        pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not POSTGRES_PASSWORD:
        logger.error("POSTGRES_PASSWORD environment variable is required")
        raise SystemExit(1)

    # Initial metric load before accepting requests
    logger.info(f"Connecting to PostgreSQL at {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
    with _cache_lock:
        _metrics_cache = _build_metrics()

    # Start background refresh thread
    t = threading.Thread(target=_refresh_loop, daemon=True)
    t.start()

    # Start HTTP server
    server = HTTPServer(("0.0.0.0", EXPORTER_PORT), MetricsHandler)
    logger.info(f"AAC Compliance Exporter listening on :{EXPORTER_PORT}/metrics")
    server.serve_forever()
