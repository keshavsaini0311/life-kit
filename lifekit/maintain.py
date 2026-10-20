"""Nightly upkeep: import statements, rebuild ledgers and learning, list what is going stale."""
from datetime import date, datetime, timedelta, timezone

from . import connections, core, learning, ledger

STALE_CONTEXT_DAYS = 30
STALE_READ_DAYS = 7
CHECKIN_GAP_DAYS = 3


def run(root, today=None):
    root, config = core.load(root)
    today = today or date.today()
    lines = ["# Maintenance " + today.isoformat(), ""]
    finance = "finance" in (config.get("domains") or []) or (root / "finance/inbox").is_dir()
    if finance:
        try:
            result = ledger.import_inbox(root)
            lines.append("Bank import: " + str(result["posted"]) + " posted, " + str(result["review"])
                         + " awaiting a rule, " + str(result["skipped_dup"]) + " duplicates skipped.")
            lines += ["- Import problem: " + e for e in result["errors"]]
        except ValueError as exc:
            lines.append("Bank import skipped: " + str(exc))
        previous = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        for month in (previous, today.strftime("%Y-%m")):
            ledger.render(root, month)
        lines.append("Ledgers rebuilt for " + previous + " and " + today.strftime("%Y-%m") + ".")
    learning.report(root, today)
    lines += ["Learning report refreshed.", "", "## Going stale", ""]
    stale = []
    for path in sorted(root.glob("*/context.md")) + [root / "personal/rules.md"]:
        if path.is_file():
            age = (today - date.fromtimestamp(path.stat().st_mtime)).days
            if age > STALE_CONTEXT_DAYS:
                stale.append(str(path.relative_to(root)) + " not updated for " + str(age) + " days.")
    records = connections.status(root)
    for conn_id in connections.enabled(root):
        record = records.get(conn_id, {})
        if record.get("status") != "ok":
            stale.append(conn_id + ": " + (record.get("status") or "configured, never verified") + ".")
        elif record.get("last_read_at"):
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(record["last_read_at"])).days
            if age > STALE_READ_DAYS:
                stale.append(conn_id + ": last verified read " + str(age) + " days ago.")
    history = core.events(root)
    checkins = [core.event_day(e) for e in history if e["kind"] == "checkin"]
    if not checkins:
        stale.append("No check-in recorded yet.")
    elif (today - max(checkins)).days >= CHECKIN_GAP_DAYS:
        stale.append("No check-in for " + str((today - max(checkins)).days) + " days.")
    month = today.strftime("%Y-%m")
    if not any(e["kind"] == "spend" and core.event_day(e).strftime("%Y-%m") == month for e in history):
        stale.append("Spending this month: unknown (no records), not zero.")
    lines += ["- " + s for s in stale] or ["Nothing stale."]
    path = root / ".local/reports" / ("maintenance-" + today.isoformat() + ".md")
    core.private_write(path, "\n".join(lines) + "\n")
    return path
