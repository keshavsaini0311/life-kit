"""Deterministic learning report: what converts, per channel and variant, from explicit action IDs only."""
from datetime import date

from . import core

MIN_N = 5          # below this, a rate is noise
MIN_AGE_DAYS = 7   # newer actions have not had time to get an answer
FOLLOW_UP_DAYS = 14
KEY_STAGES = ("reply", "referral", "interview", "offer")


def report(root, today=None):
    root, _ = core.load(root)
    today = today or date.today()
    history = core.events(root)
    actions = [e for e in history if e["kind"] == "action"]
    outcomes = {}
    for e in history:
        if e["kind"] == "outcome":
            outcomes.setdefault(e["action_id"], set()).add(e["stage"])
    groups = {}
    for a in actions:
        groups.setdefault((a["channel"], a.get("variant", "unrecorded")), []).append(a)
    lines = ["# Learning report " + today.isoformat(), "",
             "Generated from learning/events.jsonl. Each outcome credits only its explicit action ID; one count per",
             "action per stage. Rates need " + str(MIN_N) + "+ actions at least " + str(MIN_AGE_DAYS) + " days old.",
             "No outcome is unknown, not a confirmed failure. Correlation here is not proof of cause.", "",
             "## By channel and variant", ""]
    if not groups:
        lines.append("No actions recorded yet. Record real sends with `life-kit action`.")
    for (channel, variant), items in sorted(groups.items()):
        eligible = [a for a in items if (today - core.event_day(a)).days >= MIN_AGE_DAYS]
        recent = len(items) - len(eligible)
        head = "- " + channel + " / " + variant + ": " + str(len(eligible)) + " eligible, " + str(recent) + " too recent"
        if len(eligible) < MIN_N:
            lines.append(head + " — too few to compare")
            continue
        rates = []
        for stage in KEY_STAGES:
            hits = sum(1 for a in eligible if stage in outcomes.get(a["id"], ()))
            rates.append(stage + " " + str(hits) + "/" + str(len(eligible)) + " (" + str(round(100 * hits / len(eligible))) + "%)")
        lines.append(head + " — " + ", ".join(rates))
    lines += ["", "## Follow-up candidates", "",
              "Actions older than " + str(FOLLOW_UP_DAYS) + " days with no recorded outcome. Check the thread before following up.", ""]
    stale = [a for a in actions if (today - core.event_day(a)).days > FOLLOW_UP_DAYS and a["id"] not in outcomes]
    lines += ["- " + a["id"] + ": " + a["channel"] + " → " + a["target"] + " (" + str((today - core.event_day(a)).days)
              + " days)" for a in stale] or ["None."]
    path = root / "learning/reports" / (today.isoformat() + ".md")
    core.private_write(path, "\n".join(lines) + "\n")
    return path
