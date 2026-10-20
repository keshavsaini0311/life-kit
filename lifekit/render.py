"""Write workspace context and shared skills from setup answers, never clobbering user edits."""
from datetime import date
import hashlib
import json
import os
from pathlib import Path
from string import Template

from . import core, questions

TEMPLATES = Path(__file__).resolve().parent / "templates"
ALWAYS_SKILLS = ["life", "daily", "learn", "life-review"]
SKILLS_BY_DOMAIN = {"personal": [], "finance": ["finance"], "work": ["work"], "learning": ["study"]}
FILES = [("AGENTS.md", "AGENTS.md", None), ("CLAUDE.md", "CLAUDE.md", None), ("LIFE.md", "LIFE.md", None),
         ("rules.md", "personal/rules.md", None), ("MEMORY.md", "memory/MEMORY.md", None),
         ("personal.md", "personal/context.md", "personal"), ("now.md", "personal/now.md", "personal"),
         ("finance.md", "finance/context.md", "finance"),
         ("learning.md", "learning/context.md", "learning"), ("plan.md", "learning/plan.md", "learning"),
         ("work.md", "work/context.md", "work"), ("standup.md", "work/standup.md", "work")]
DIRS = {None: ["learning/reports"], "finance": ["finance/inbox", "finance/imports", "finance/ledger"]}
AREAS = {
    "personal": ("Personal", "`personal/`", "(context layer)", "Goals, routine, health, people and daily notes."),
    "finance": ("Finance", "`finance/`", "`finance`", "Income, spending, ledger, investments and goals."),
    "learning": ("Learning", "`learning/`", "`study`, `learn`", "Learning goals, study sessions and activity outcomes."),
    "work": ("Work", "`work/`", "`work`", "Standups, tickets, PRs and service health. Read-only."),
}
ROUTES = [
    (None, '"daily run" or "review today"', "`daily`"),
    (None, '"how am I doing" or anything spanning areas', "`life`"),
    (None, '"what is working" or "review the week"', "`learn`"),
    ("finance", '"I spent X", "salary came", "can I afford"', "`finance`"),
    ("learning", '"teach me", "test my understanding", "what should I study"', "`study`"),
    ("work", '"standup", "what did I ship", "my tickets"', "`work`"),
    ("personal", "family, health, gym or daily routine", "`personal/` under the rules file"),
]
LOGS = {"finance": ["| Monthly ledger (generated) | `finance/ledger/YYYY-MM.md` |"],
        "learning": ["| Study sessions | `learning/plan.md` |"],
        "personal": ["| Personal, per day | `personal/now.md` |"],
        "work": ["| Standup | `work/standup.md` |"]}


def _fmt(value):
    if value is None or value == "" or value == []:
        return "unknown"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(value)
    return str(value)


def values(root, answers):
    domains = [d for d in (answers.get("domains.enabled") or []) if d in AREAS]
    result = {q["id"].replace(".", "_"): _fmt(answers.get(q["id"])) for q in questions.QUESTIONS}
    result.update(name=answers.get("basics.name") or "you", workspace=str(root), today=date.today().isoformat())
    result["domain_table"] = "\n".join("| " + " | ".join(AREAS[d]) + " |" for d in domains) or "| (none yet) | | | |"
    result["routing_table"] = "\n".join("| " + phrase + " | " + target + " |" for d, phrase, target in ROUTES
                                        if d is None or d in domains)
    result["log_table"] = "\n".join(row for d in domains for row in LOGS.get(d, []))
    return result


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_new(root, rel, text, rendered):
    """Write unless the user edited the file; then write REL.suggested. Returns the path written or None."""
    path = Path(root) / rel
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == text:
            rendered[rel] = _digest(text)
            return None
        if _digest(current) != rendered.get(rel) and current not in core.blank_files().values():
            core.private_write(path.with_name(path.name + ".suggested"), text)
            return rel + ".suggested"
    core.private_write(path, text)
    rendered[rel] = _digest(text)
    return rel


def skills_for(domains):
    names = list(ALWAYS_SKILLS)
    for domain in domains:
        names += [n for n in SKILLS_BY_DOMAIN.get(domain, []) if n not in names]
    return names


def _link_claude_skills(root, rendered, put):
    link = Path(root) / ".claude/skills"
    if link.is_symlink():
        return
    if not link.exists():
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(os.path.join("..", ".agents", "skills"), str(link), target_is_directory=True)
            return
        except OSError:  # e.g. Windows without developer mode: keep a copy instead
            pass
    # A real folder (copy fallback, or the user's own skills): copy file by file, never over edits.
    source = Path(root) / ".agents/skills"
    for path in sorted(source.rglob("*")):
        if path.is_file():
            put(".claude/skills/" + path.relative_to(source).as_posix(), path.read_text(encoding="utf-8"))


def apply(root, answers):
    root = Path(root).expanduser().resolve()
    domains = [d for d in (answers.get("domains.enabled") or []) if d in AREAS]
    mapping = values(root, answers)
    record = root / ".local/rendered.json"
    rendered = json.loads(record.read_text(encoding="utf-8")) if record.is_file() else {}
    written = []

    def put(rel, text):
        result = write_new(root, rel, text, rendered)
        if result:
            written.append(result)

    for template, dest, domain in FILES:
        if domain is None or domain in domains:
            put(dest, Template((TEMPLATES / "context" / template).read_text(encoding="utf-8")).substitute(mapping))
    if "finance" in domains and not (root / "finance/rules.json").exists():
        put("finance/rules.json", "[]\n")
    for domain, folders in DIRS.items():
        if domain is None or domain in domains:
            for folder in folders:
                (root / folder).mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in skills_for(domains):
        for source in sorted((TEMPLATES / "skills" / name).rglob("*")):
            if source.is_file():
                rel = ".agents/skills/" + name + "/" + source.relative_to(TEMPLATES / "skills" / name).as_posix()
                put(rel, Template(source.read_text(encoding="utf-8")).substitute(mapping))
    _link_claude_skills(root, rendered, put)
    core.private_write(record, core.json_text(rendered))
    return written
