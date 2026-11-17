"""winrm_eventlog.py — Custom EDA event source for Windows Event Log

Polls a remote Windows host via WinRM, fetches new events from one or more
event logs since the last poll, and emits each event as a dict to the EDA
rule engine.

ARGUMENTS
    host:           Windows host (FQDN or IP). Required.
    port:           WinRM port. Default 5985.
    scheme:         http | https. Default http (basic auth on 5985).
    username:       Windows user. Required.
    password:       Windows password (or use cert auth). Required.
    transport:      basic | ntlm | kerberos. Default basic.
    log_names:      List of event log channels to poll. Default ["Security",
                    "Application", "System", "Microsoft-Windows-Windows
                    Defender/Operational"].
    event_ids:      Optional list of event IDs to filter to (server-side
                    filter via XPath). If empty, all events are returned.
    interval:       Poll interval in seconds. Default 10.
    max_events:     Max events per poll per log. Default 50.

EMITTED EVENT SHAPE
    {
        "event_source":  "winrm_eventlog",
        "host":          "<host>",
        "log_name":      "Microsoft-Windows-Windows Defender/Operational",
        "event_id":      5007,
        "provider_name": "Microsoft-Windows-Windows Defender",
        "record_id":     143,
        "level":         "Warning",
        "time_created":  "2026-05-28T16:00:38Z",
        "machine_name":  "EC2AMAZ-XXXXXX",
        "message":       "Windows Defender Real-Time Protection feature has been changed...",
        "raw_xml":       "<Event>...</Event>"   # only included if include_raw=true
    }

EXAMPLE RULEBOOK USAGE
    sources:
      - lab.eda.winrm_eventlog:
          host:      "{{ windows_host }}"
          username:  "{{ windows_admin }}"
          password:  "{{ windows_password }}"
          event_ids: [5007, 5025, 4719, 4956]
          interval:  10

REFERENCES
    - Defender Realtime change:  Microsoft-Windows-Windows Defender id=5007
    - Firewall service stopped:  System            id=7036 (service control)
    - Audit policy changed:      Security          id=4719
    - Firewall settings restored: Microsoft-Windows-Windows Firewall id=2003
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

LOGGER = logging.getLogger(__name__)

# Namespace used in Windows Event Log XML
_EVENT_NS = "{http://schemas.microsoft.com/win/2004/08/events/event}"


def _xpath_filter(event_ids: Optional[List[int]]) -> str:
    """Return an XPath filter for Get-WinEvent's -FilterXPath parameter.

    With no event IDs, returns "*" (all events). Otherwise returns a filter
    that only matches events whose System/EventID matches one in the list.
    """
    if not event_ids:
        return "*"
    clauses = " or ".join(f"EventID={eid}" for eid in event_ids)
    return f"*[System[({clauses})]]"


def _parse_event_json(json_str: str, host: str, log_name: str) -> Dict[str, Any]:
    """Parse a single Windows Event (emitted as JSON by our PowerShell) into a
    flat dict for EDA. Using JSON instead of EventRecord.ToXml() means we get
    the fully-rendered `Message` field, which downstream rule conditions
    substring-match on."""
    import json as _json
    raw = _json.loads(json_str)
    return {
        "event_source": "winrm_eventlog",
        "host":         host,
        "log_name":     log_name,
        "event_id":     int(raw.get("EventId") or 0),
        "provider_name": raw.get("ProviderName"),
        "record_id":    int(raw.get("RecordId") or 0),
        "level":        raw.get("LevelDisplayName"),
        "time_created": raw.get("TimeCreated"),
        "machine_name": raw.get("MachineName"),
        "message":      (raw.get("Message") or "").strip(),
    }


def _build_powershell(log_name: str, xpath: str, max_events: int,
                      last_record_id: int) -> str:
    """Build the PowerShell that fetches events newer than last_record_id.

    Two important design notes:

    1. The RecordId filter is applied server-side via XPath
       (`EventRecordID > N`) — NOT client-side after -MaxEvents truncation.
       That way, a burst of events between polls can't silently drop older
       events just because they fall outside the newest -MaxEvents window.

    2. PowerShell emits one JSON object per event (NOT EventRecord.ToXml()).
       ToXml() omits the fully-rendered Message, which would leave downstream
       EDA rule substring-matches against `event.message` evaluating against
       an empty string. JSON gives us the rendered Message directly.
    """
    # If a base XPath filter (e.g. event_id list) is "*" we still need the
    # RecordID guard; combine the two predicates explicitly.
    if xpath in ("*", ""):
        combined_xpath = f"*[System[EventRecordID > {last_record_id}]]"
    else:
        # xpath is like "*[System[(EventID=5007 or EventID=2003)]]"
        # We want to AND in the RecordID guard inside System[...].
        # Replace the trailing "]]" with " and EventRecordID > N]]" — only
        # for our well-known builder output.
        if xpath.endswith("]]"):
            combined_xpath = xpath[:-2] + f" and EventRecordID > {last_record_id}]]"
        else:
            combined_xpath = f"({xpath}) and *[System[EventRecordID > {last_record_id}]]"

    return (
        "$ErrorActionPreference='SilentlyContinue';"
        f"$evs = Get-WinEvent -LogName '{log_name}' -FilterXPath \"{combined_xpath}\" "
        f"-MaxEvents {max_events} -ErrorAction SilentlyContinue -ErrorVariable ge;"
        "if ($evs) {"
        " $evs | Sort-Object RecordId |"
        " ForEach-Object {"
        "   $o = [PSCustomObject]@{"
        "     EventId          = $_.Id;"
        "     ProviderName     = $_.ProviderName;"
        "     RecordId         = $_.RecordId;"
        "     LevelDisplayName = $_.LevelDisplayName;"
        "     TimeCreated      = ($_.TimeCreated.ToUniversalTime().ToString('o'));"
        "     MachineName      = $_.MachineName;"
        "     Message          = $_.Message;"
        "   };"
        "   ($o | ConvertTo-Json -Compress -Depth 4) + '<<<END_OF_EVENT>>>'"
        " }"
        "}"
        # Surface PowerShell errors on stdout and always exit 0. A poll that
        # finds no matching events is the normal case, not a failure: when the
        # suppressed Get-WinEvent error is the last statement PowerShell exits 1
        # and every quiet poll was being logged as a failed WinRM call.
        ";if ($ge) { foreach ($e in $ge) { Write-Output ('<<<PS_ERROR>>>' + $e.Exception.Message) } }"
        ";exit 0"
    )


async def _winrm_run(host: str, port: int, scheme: str, username: str,
                     password: str, transport: str, ps: str) -> str:
    """Run a PowerShell snippet on the remote host via WinRM.

    Off-loads the blocking pywinrm call to an executor so the asyncio loop
    is not blocked while polling.
    """
    try:
        import winrm  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "pywinrm is required for the winrm_eventlog event source. "
            "Install with: pip install pywinrm"
        ) from exc

    def _run() -> str:
        endpoint = f"{scheme}://{host}:{port}/wsman"
        session = winrm.Session(
            endpoint,
            auth=(username, password),
            transport=transport,
            server_cert_validation="ignore",
            # A hung WinRM call must raise so the poll loop keeps going; without
            # these the source has been seen to stall silently for minutes.
            operation_timeout_sec=15,
            read_timeout_sec=30,
        )
        result = session.run_ps(ps)
        if result.status_code != 0:
            err = (result.std_err or b"").decode(errors="replace")
            raise RuntimeError(f"WinRM PowerShell failed: {err}")
        return (result.std_out or b"").decode(errors="replace")

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run)


async def main(queue: asyncio.Queue, args: Dict[str, Any]) -> None:
    """EDA event-source entry point.

    Polls the configured event logs on `interval`, parses new events, and
    pushes them onto `queue` for the rule engine to consume.
    """
    host       = args["host"]
    port       = int(args.get("port", 5985))
    scheme     = args.get("scheme", "http")
    username   = args["username"]
    password   = args["password"]
    transport  = args.get("transport", "basic")
    log_names: List[str] = args.get("log_names") or [
        "Security",
        "System",
        "Application",
        "Microsoft-Windows-Windows Defender/Operational",
        "Microsoft-Windows-Windows Firewall With Advanced Security/Firewall",
    ]
    event_ids  = args.get("event_ids") or []
    interval   = float(args.get("interval", 10))
    max_events = int(args.get("max_events", 50))

    xpath = _xpath_filter([int(e) for e in event_ids])

    # Track the last seen RecordId per log so we only emit new events.
    # The first poll of each log only PRIMES the bookmark: it records the newest
    # RecordId and emits nothing. Without this every activation (re)start replayed
    # up to max_events historical events per log and fired the enforcement
    # workflow once per replayed event. Only events written after the start are emitted.
    last_seen: Dict[str, int] = {log: 0 for log in log_names}
    primed: Dict[str, bool] = {log: False for log in log_names}

    LOGGER.info("winrm_eventlog source starting: host=%s logs=%s ids=%s "
                "interval=%ss", host, log_names, event_ids, interval)

    while True:
        for log_name in log_names:
            try:
                ps = _build_powershell(
                    log_name=log_name,
                    xpath=xpath,
                    max_events=max_events,
                    last_record_id=last_seen[log_name],
                )
                stdout = await _winrm_run(
                    host=host, port=port, scheme=scheme,
                    username=username, password=password,
                    transport=transport, ps=ps,
                )
            except Exception:  # noqa: BLE001
                LOGGER.exception("WinRM poll failed for log=%s", log_name)
                continue

            # "No events were found" is the normal empty poll. Any other PowerShell
            # error is logged. Events that did come back are still emitted and still
            # move the bookmark, so an error that accompanies real data cannot blind
            # the source; but an errored poll that returned nothing is skipped without
            # touching the bookmark, so a failed first poll cannot prime at zero and
            # replay history once the query recovers.
            ps_errors = [
                ln[len("<<<PS_ERROR>>>"):].strip()
                for ln in stdout.splitlines() if ln.startswith("<<<PS_ERROR>>>")
            ]
            real_errors = [m for m in ps_errors if "No events were found" not in m]
            for msg in real_errors:
                LOGGER.warning("PowerShell error on log=%s: %s", log_name, msg[:300])

            events = []
            for chunk in stdout.split("<<<END_OF_EVENT>>>"):
                chunk = chunk.strip()
                if not chunk or not chunk.startswith("{"):
                    continue
                try:
                    events.append(_parse_event_json(chunk, host=host, log_name=log_name))
                except (ValueError, KeyError):
                    LOGGER.warning("Could not parse Windows event JSON: %s",
                                   chunk[:200])
            if real_errors and not events:
                continue

            for evt in events:
                rec = evt.get("record_id", 0)
                if rec > last_seen[log_name]:
                    last_seen[log_name] = rec
                if primed[log_name]:
                    await queue.put(evt)
            if not primed[log_name]:
                primed[log_name] = True
                LOGGER.info("winrm_eventlog primed log=%s at record_id=%s (history not replayed)",
                            log_name, last_seen[log_name])

        await asyncio.sleep(interval)


# Convenience for testing the source standalone (outside ansible-rulebook)
if __name__ == "__main__":  # pragma: no cover
    import json
    import os

    async def _dump():
        q: asyncio.Queue = asyncio.Queue()
        cfg = {
            "host":       os.environ["WIN_HOST"],
            "username":   os.environ["WIN_USER"],
            "password":   os.environ["WIN_PASS"],
            "event_ids":  [5007, 5025, 4719, 7036, 2003],
            "interval":   5,
            "log_names": [
                "Microsoft-Windows-Windows Defender/Operational",
                "System",
                "Security",
            ],
        }
        task = asyncio.create_task(main(q, cfg))
        try:
            while True:
                evt = await q.get()
                print(json.dumps(evt, default=str, indent=2))
        except KeyboardInterrupt:
            task.cancel()

    asyncio.run(_dump())
