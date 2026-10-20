"""Bank CSV import, rule-based posting and generated monthly ledgers.

Debits matching a category rule post automatically as observed (`bank-csv`) spend. Transfers,
investments, income and credits never count as spend. Unmatched debits wait in
finance/imports/pending.json and review.md until a rule matches; nothing is guessed.
"""
import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

from . import core

ALIASES = {
    "date": ("date", "txn date", "transaction date", "tran date", "posting date", "value date", "value dt"),
    "description": ("narration", "description", "particulars", "transaction details", "details", "remarks"),
    "debit": ("withdrawal amt.", "withdrawal amount", "withdrawal", "withdrawals", "debit amount", "debit", "dr"),
    "credit": ("deposit amt.", "deposit amount", "deposit", "deposits", "credit amount", "credit", "cr"),
    "balance": ("closing balance", "balance"),
    "ref": ("chq./ref.no.", "ref no./cheque no.", "reference", "ref no", "ref", "chq no", "cheque no"),
}
# ponytail: day-first dates only; add a per-workspace format setting for month-first (US) statements
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%d %b %Y", "%d-%b-%Y", "%d %b %y", "%d-%b-%y")
PENDING = "finance/imports/pending.json"


def _norm(cell):
    return " ".join(str(cell).strip().lower().split())


def _columns(header):
    names = [_norm(c) for c in header]
    found = {}
    for field, aliases in ALIASES.items():
        for alias in aliases:
            if alias in names:
                found[field] = names.index(alias)
                break
    return found if {"date", "description"} <= set(found) and ({"debit", "credit"} & set(found)) else None


def _date(text):
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError("unrecognised date " + repr(text))


def _amount(text):
    cleaned = "".join(ch for ch in str(text) if ch.isdigit() or ch in ".-")
    if not cleaned:
        return None
    value = Decimal(cleaned)
    if not value.is_finite() or value != value.quantize(Decimal("0.01")):
        raise ValueError("amount needs at most two decimals: " + repr(text))
    return abs(value) if value else None


def parse_csv(path):
    """Return (rows, errors). Any error means the whole file is left for review."""
    with open(path, newline="", encoding="utf-8-sig") as stream:
        table = list(csv.reader(stream))
    for index, header in enumerate(table):
        columns = _columns(header)
        if columns:
            break
    else:
        return [], ["no recognisable header (need date, description and debit/credit columns)"]
    rows, errors = [], []
    for number, cells in enumerate(table[index + 1:], index + 2):
        get = lambda field: cells[columns[field]].strip() if field in columns and columns[field] < len(cells) else ""
        if not any(c.strip() for c in cells) or (not get("date") and not get("debit") and not get("credit")):
            continue  # blank lines and statement footers
        try:
            rows.append({"date": _date(get("date")), "description": get("description"),
                         "debit": _amount(get("debit")), "credit": _amount(get("credit")),
                         "balance": get("balance"), "ref": get("ref")})
        except (ValueError, InvalidOperation) as exc:
            errors.append("line " + str(number) + ": " + str(exc))
    return rows, errors


def load_rules(root):
    path = Path(root) / "finance/rules.json"
    rules = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    for rule in rules:
        if not isinstance(rule, dict) or not str(rule.get("match", "")).strip() or not (rule.get("category") or rule.get("kind")):
            raise ValueError("finance/rules.json: each rule needs \"match\" and a \"category\" or \"kind\".")
        if rule.get("kind") and rule["kind"] not in ("transfer", "investment", "income"):
            raise ValueError("finance/rules.json: kind must be transfer, investment or income.")
    return rules


def match(rules, description):
    text = description.lower()
    return next((r for r in rules if str(r["match"]).lower() in text), None)


def _pending(root):
    path = Path(root) / PENDING
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def import_inbox(root):
    root, _ = core.load(root)
    rules = load_rules(root)
    pending = _pending(root)
    result = {"posted": 0, "review": 0, "skipped_dup": 0, "errors": []}
    inbox = root / "finance/inbox"
    for path in sorted(inbox.glob("*.csv")) if inbox.is_dir() else []:
        rows, errors = parse_csv(path)
        if errors:
            result["errors"] += [path.name + ": " + e for e in errors]
            continue
        seen = {}
        for row in rows:
            if not row["debit"]:
                continue  # credits are never spending
            base = [row["date"], format(row["debit"], ".2f"), row["ref"] or row["description"]]
            seen[tuple(base)] = seen.get(tuple(base), -1) + 1  # nth identical row in this file
            key = hashlib.sha256(json.dumps(base + [seen[tuple(base)]]).encode()).hexdigest()[:24]
            pending.setdefault(key, dict(row, debit=format(row["debit"], ".2f"),
                                         credit=format(row["credit"], ".2f") if row["credit"] else None))
        done = inbox / "processed"
        done.mkdir(exist_ok=True)
        target = done / path.name
        while target.exists():
            target = target.with_name("1-" + target.name)
        path.replace(target)
    posted = {e.get("ref") for e in core.events(root) if e["kind"] == "spend" and e.get("source") == "bank-csv"}
    for key, row in list(pending.items()):
        if key in posted:
            del pending[key]
            result["skipped_dup"] += 1
            continue
        rule = match(rules, row["description"])
        if rule is None:
            continue
        if not rule.get("kind"):
            core.spend(root, row["debit"], rule["category"], note=row["description"], request_id="bank-" + key,
                       source="bank-csv", ref=key, on=row["date"])
            result["posted"] += 1
        del pending[key]
    core.private_write(root / PENDING, core.json_text(pending))
    lines = ["# Bank rows awaiting a rule", "",
             "These debits are not counted anywhere yet. Add a rule to `finance/rules.json`, e.g.",
             '`{"match": "shop name", "category": "shopping"}` or `{"match": "to self", "kind": "transfer"}`;',
             "the next `life-kit maintain` posts them. Kinds transfer/investment/income are never spending.", "",
             "| Date | Description | Amount | Key |", "|---|---|---|---|"]
    lines += ["| " + r["date"] + " | " + r["description"].replace("|", "/") + " | " + r["debit"] + " | " + k + " |"
              for k, r in sorted(pending.items(), key=lambda kv: kv[1]["date"])]
    core.private_write(root / "finance/imports/review.md", "\n".join(lines) + "\n")
    result["review"] = len(pending)
    return result


def render(root, month):
    root, _ = core.load(root)
    first = date.fromisoformat(month + "-01")
    spends = sorted((e for e in core.events(root) if e["kind"] == "spend"
                     and core.event_day(e).strftime("%Y-%m") == month), key=lambda e: (core.event_day(e), e["at"]))
    waiting = sum(1 for r in _pending(root).values() if r["date"].startswith(month))
    lines = ["<!-- generated by life-kit; edit events or finance/rules.json, not this file -->",
             "# Ledger " + first.strftime("%B %Y"), "", "Generated: " + core.timestamp(), ""]
    if spends:
        totals, categories = {}, {}
        for e in spends:
            totals[e["currency"]] = totals.get(e["currency"], Decimal(0)) + Decimal(e["amount"])
            key = (e["category"], e["currency"])
            categories[key] = categories.get(key, Decimal(0)) + Decimal(e["amount"])
        lines += ["Recorded spending: " + ", ".join(c + " " + format(v, ".2f") for c, v in sorted(totals.items())),
                  "Recorded is not complete: it includes only bank rows matched by rules and spending you logged.", "",
                  "## By category", "", "| Category | Amount |", "|---|---|"]
        lines += ["| " + cat + " | " + cur + " " + format(v, ".2f") + " |" for (cat, cur), v in sorted(categories.items())]
        lines += ["", "## Entries", "", "| Day | Amount | Category | Note | Source |", "|---|---|---|---|---|"]
        lines += ["| " + core.event_day(e).isoformat() + " | " + e["currency"] + " " + e["amount"] + " | " + e["category"]
                  + " | " + e.get("note", "").replace("|", "/") + " | " + e["source"] + " |" for e in spends]
    else:
        lines.append("Spending: unknown, not zero. No spend records for this month.")
    if waiting:
        lines += ["", str(waiting) + " bank row" + (" awaiting a rule" if waiting == 1 else "s awaiting a rule")
                  + " (not counted): see finance/imports/review.md."]
    path = root / "finance/ledger" / (month + ".md")
    core.private_write(path, "\n".join(lines) + "\n")
    return path
