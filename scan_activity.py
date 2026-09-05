from __future__ import annotations

import html
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

IST = ZoneInfo("Asia/Kolkata")


def _render(slot, lines, status="RUNNING", error=False):
    body = "".join(f"<div class='scan-log-line'>{html.escape(line)}</div>" for line in lines[-12:])
    status_class = "error" if error else ("done" if status == "COMPLETE" else "live")
    slot.markdown(
        f"""
        <div class='scan-activity {status_class}'>
          <div class='scan-activity-head'><span>SCAN ACTIVITY</span><b>{status}</b></div>
          <div class='scan-activity-body'>{body}</div>
        </div>
        <style>
        .scan-activity{{position:fixed;right:16px;bottom:16px;width:min(350px,calc(100vw - 32px));z-index:999999;background:#090d12;border:1px solid #27313d;border-radius:7px;box-shadow:0 8px 28px rgba(0,0,0,.42);font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;color:#aeb8c5;overflow:hidden}}
        .scan-activity-head{{display:flex;justify-content:space-between;align-items:center;padding:6px 9px;border-bottom:1px solid #202934;background:#0d131a;font-size:9px;letter-spacing:.10em;color:#778292}}
        .scan-activity-head b{{font-size:8px;color:#35d07f;font-weight:600}}
        .scan-activity.error .scan-activity-head b{{color:#ff6673}}
        .scan-activity-body{{padding:7px 9px;max-height:195px;overflow:hidden;font-size:9px;line-height:1.55}}
        .scan-log-line{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
        .scan-log-line::before{{content:'› ';color:#4d5968}}
        .scan-activity-body .scan-log-line:last-child{{color:#d6dde6}}
        @media(max-width:700px){{.scan-activity{{right:8px;bottom:8px;width:calc(100vw - 16px)}}}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def install_scan_activity():
    """Install a small live terminal-style monitor around the existing stock scan."""
    import rs_engine

    if getattr(rs_engine, "_scan_activity_installed", False):
        return

    original_run_scan = rs_engine.run_scan

    def wrapped_run_scan(*args, **kwargs):
        slot = st.empty()
        lines = []
        started = time.perf_counter()
        mode = str(kwargs.get("snapshot_mode", "eod")).upper()
        lines.append(f"{datetime.now(IST):%H:%M:%S}  [START] {mode} scan")
        _render(slot, lines)

        original_callback = kwargs.get("progress_callback")
        last_message = {"value": ""}

        def activity_callback(done, total, message):
            msg = str(message)
            now = datetime.now(IST).strftime("%H:%M:%S")
            upper = msg.upper()

            if msg != last_message["value"]:
                should_log = True
                if "Downloading" in msg and "batch" in msg:
                    try:
                        batch_no = int(msg.split("batch", 1)[1].strip().split("/", 1)[0])
                        should_log = batch_no == 1 or batch_no % 5 == 0
                    except Exception:
                        pass

                if should_log:
                    if "NSE" in upper:
                        prefix = "NSE"
                    elif "RECOVERY" in upper or "STALE" in upper:
                        prefix = "REC"
                    elif "READY" in upper or "APPLIED" in upper:
                        prefix = "OK"
                    elif "ERROR" in upper or "FAILED" in upper:
                        prefix = "ERROR"
                    else:
                        prefix = ".."
                    lines.append(f"{now}  [{prefix}] {msg}")
                    lines[:] = lines[-12:]
                last_message["value"] = msg

            # The NSE bhavcopy is a synchronous request, so there is no honest
            # byte-level percentage available. Keep the main progress bar at a
            # visible stage position while the request is in flight instead of
            # showing 0% and then jumping straight to 100%.
            if original_callback:
                if "LOADING LATEST NSE BHAVCOPY" in upper:
                    original_callback(85, 100, "NSE bhavcopy · fetching")
                elif "NSE LATEST CLOSE APPLIED" in upper:
                    original_callback(100, 100, msg)
                else:
                    original_callback(done, total, message)
            _render(slot, lines)

        kwargs["progress_callback"] = activity_callback
        try:
            result = original_run_scan(*args, **kwargs)
            elapsed = time.perf_counter() - started
            result_df, stats = result if isinstance(result, tuple) else (None, {})
            matches = len(result_df) if result_df is not None else "?"
            stale = int(stats.get("stale_data_count", 0) or 0)
            missing = int(stats.get("missing_count", 0) or 0)
            short_history = int(stats.get("short_history_count", 0) or 0)

            # Always record data-integrity diagnostics in the activity log.
            # The detailed stale/date-distribution diagnostics remain available
            # in the Stock RS page; they are intentionally not removed when the
            # current scan has zero stale symbols.
            if stale:
                lines.append(f"{datetime.now(IST):%H:%M:%S}  [WARN] {stale} stale symbols remain")
            else:
                lines.append(f"{datetime.now(IST):%H:%M:%S}  [OK] Stale data · 0")
            if missing:
                lines.append(f"{datetime.now(IST):%H:%M:%S}  [WARN] {missing} symbols missing")
            else:
                lines.append(f"{datetime.now(IST):%H:%M:%S}  [OK] Missing symbols · 0")
            if short_history:
                lines.append(f"{datetime.now(IST):%H:%M:%S}  [WARN] {short_history} short/stale history symbols")
            lines.append(f"{datetime.now(IST):%H:%M:%S}  [OK] Results ready · {matches} matches · {elapsed:.1f}s")
            _render(slot, lines, status="COMPLETE")
            return result
        except Exception as exc:
            lines.append(f"{datetime.now(IST):%H:%M:%S}  [ERROR] {type(exc).__name__}: {exc}")
            _render(slot, lines, status="ERROR", error=True)
            raise

    rs_engine.run_scan = wrapped_run_scan
    rs_engine._scan_activity_installed = True
