"""Every setup question, explained. The wizard and docs/setup-guide.md both come from here.

Each question: id, section, prompt, why (why we ask), example, skip (what skipping means),
kind (text|choice|multi|time|times|number|yesno|secret|path), optional choices,
optional when(answers) + when_text, optional default(answers) for detected values.
Later modules append their own sections' questions with `extend`.
"""
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
import re

DOMAIN_CHOICES = ("personal", "finance", "career", "work")

SECTIONS = [
    ("basics", "Basics", "Who you are and where your workspace lives. Two minutes."),
    ("domains", "Life areas", "Pick the parts of life you want help with. You can add more later by re-running setup."),
    ("rules", "Rules and routine", "Your boundaries and rhythm. Every assistant reads these before doing anything."),
    ("personal", "Personal context", "A short portrait so suggestions fit your real life."),
    ("finance", "Money", "Numbers are stored with today's date, so nobody mistakes an old number for a current one."),
    ("career", "Career", "Your current job, where you want to go, and how you prepare."),
    ("work", "Day job", "Context for standups, tickets and work briefs."),
    ("assistants", "AI assistants", "Which assistant apps should read this workspace. Both can share the same skills."),
    ("plugins", "Claude Code plugins", "Optional add-ons for Claude Code. Pick what you like; none are required."),
    ("connections", "Connections", "Optional accounts your assistant may read: mail, calendar, work tools, broker, shopping."),
    ("runners", "Scheduled runs", "Jobs your computer runs on its own at times you choose. Reports stay on this computer."),
    ("telegram", "Phone (Telegram)", "Optional: control Life Kit and get 'report ready' pings from your phone."),
]


def _domain(name):
    return lambda a: name in (a.get("domains.enabled") or [])


def _detected_timezone(_answers):
    if os.environ.get("TZ"):
        return os.environ["TZ"]
    try:
        target = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in target:
            return target.split("zoneinfo/", 1)[1]
    except OSError:
        pass
    return None


def _detected_assistants(_answers):
    import shutil
    found = [name for name in ("claude", "codex") if shutil.which(name)]
    return ",".join(found) or None


def _q(id, section, prompt, why, example, skip, kind="text", **extra):
    return dict(id=id, section=section, prompt=prompt, why=why, example=example, skip=skip, kind=kind, **extra)


SKIP_UNKNOWN = "Recorded as unknown. Assistants will ask instead of guessing."

QUESTIONS = [
    _q("basics.currency", "basics", "Which currency do you use? (3-letter code)",
       "Money is stored exactly in one currency; amounts in different currencies are never added together.",
       "INR, USD, EUR, GBP", "Cannot be skipped: the workspace needs it.", "currency"),
    _q("basics.name", "basics", "What should assistants call you?",
       "Skills and reports address you by this name instead of 'the user'.",
       "Priya", "Assistants will say 'you'."),
    _q("basics.timezone", "basics", "What is your timezone?",
       "Dates like 'today' and 'this week' depend on it. Schedules use your computer's clock.",
       "Asia/Kolkata, Europe/London, America/New_York", SKIP_UNKNOWN, "timezone",
       default=_detected_timezone),
    _q("domains.enabled", "domains", "Which life areas do you want? (comma-separated numbers or names)",
       "Each area gets its own folder, skills and optional scheduled runs. Unpicked areas stay out of the way.",
       "personal, finance, career", "Only the core check-in, spending and review commands are set up.", "multi",
       choices=list(DOMAIN_CHOICES)),

    _q("rules.work_hours", "rules", "When are you usually busy with work or study?",
       "Assistants avoid suggesting tasks in these hours.",
       "Mon-Fri 10:00-19:00", SKIP_UNKNOWN),
    _q("rules.free_time", "rules", "When do you realistically have free time on a normal day?",
       "Plans that ignore your real time get abandoned. Suggestions fit inside this.",
       "45 minutes after dinner, more on Sundays", SKIP_UNKNOWN),
    _q("rules.review_time", "rules", "What time suits a short daily review? (HH:MM, 24-hour)",
       "The nightly report runner defaults to this time.",
       "22:00", "The nightly report suggests 22:00; you can change it later.", "time"),
    _q("rules.privacy", "rules", "Anything that must never leave this computer or be shared?",
       "Written into your rules. Personal and money files stay local by default either way.",
       "Never mention my health to anyone; never upload bank statements",
       "The default applies: personal and finance stay local."),
    _q("rules.tone", "rules", "How should assistants talk to you?",
       "Sets the voice of reports and coaching.",
       "Direct and short. Push me when I slack.", "A neutral, concise tone."),

    _q("personal.goals", "personal", "What personal goals matter this year?",
       "Daily suggestions are checked against these.",
       "Gym 4x/week, sleep 7h, call parents on Sundays", SKIP_UNKNOWN, when=_domain("personal"),
       when_text="personal area enabled"),
    _q("personal.routine", "personal", "Describe a normal day in one or two lines.",
       "Helps assistants place reminders and prep at times that actually work.",
       "Wake 8, office 10-7, gym 8pm, dinner 9:30", SKIP_UNKNOWN, when=_domain("personal"),
       when_text="personal area enabled"),
    _q("personal.notes", "personal", "Anything else an assistant should always remember about you?",
       "Pinned in your personal context file, verbatim.",
       "I'm vegetarian; I prefer mornings for deep work", "Nothing pinned.", when=_domain("personal"),
       when_text="personal area enabled"),

    _q("finance.income_monthly", "finance", "Monthly take-home income? (number in your currency)",
       "Used for budgets and 'can I afford this' answers, dated today.",
       "90000", SKIP_UNKNOWN, "number", when=_domain("finance"), when_text="finance area enabled"),
    _q("finance.baseline_spend", "finance", "Roughly what do you spend in a month? (number)",
       "A baseline to compare actual spending against. Your own estimate, labelled as such.",
       "40000", SKIP_UNKNOWN, "number", when=_domain("finance"), when_text="finance area enabled"),
    _q("finance.goals", "finance", "What are your money goals?",
       "The finance skill prioritises advice against these.",
       "6-month emergency fund, then index funds monthly", SKIP_UNKNOWN,
       when=_domain("finance"), when_text="finance area enabled"),
    _q("finance.bank_csv", "finance", "Will you drop bank statement CSV files into finance/inbox/?",
       "Then spending is imported and posted automatically each night, using category rules you approve.",
       "yes", "No automatic import; log spending by hand or by phone.", "yesno",
       when=_domain("finance"), when_text="finance area enabled"),

    _q("career.current_role", "career", "What is your current role and experience?",
       "Job search and prep skills tailor to your level.",
       "Backend engineer, 2 years, Node + Postgres", SKIP_UNKNOWN,
       when=_domain("career"), when_text="career area enabled"),
    _q("career.target", "career", "What role and pay are you aiming for, and by when?",
       "Job discovery filters by this; prep plans work back from the date.",
       "SDE-2 backend, 30L+, within 6 months", SKIP_UNKNOWN,
       when=_domain("career"), when_text="career area enabled"),
    _q("career.locations", "career", "Where can you work?",
       "Filters job listings.", "Bangalore or remote (India)", "All locations considered.",
       when=_domain("career"), when_text="career area enabled"),
    _q("career.resume_path", "career", "Path to your current resume file (PDF or source)?",
       "Applications record a fingerprint of the exact file used. The file is never uploaded by setup.",
       "~/Documents/resume.pdf", "Resume-related steps will ask for it when needed.", "path",
       when=_domain("career"), when_text="career area enabled"),
    _q("career.prep_topics", "career", "Which interview topics do you want to practise?",
       "The prep skill builds a plan from these.",
       "DSA, system design, SQL, behavioural", SKIP_UNKNOWN,
       when=_domain("career"), when_text="career area enabled"),

    _q("work.employer", "work", "Where do you work, and what is your role?",
       "Standups and work briefs use it. Stays in your private workspace.",
       "Acme Corp, backend engineer", SKIP_UNKNOWN, when=_domain("work"), when_text="work area enabled"),
    _q("work.tools", "work", "Which work tools do you use? (comma-separated)",
       "Suggests matching connections later.",
       "github, slack, clickup", "No work tools suggested.", "multi",
       choices=["github", "gitlab", "slack", "clickup", "jira", "linear", "notion", "signoz", "other"],
       when=_domain("work"), when_text="work area enabled"),
    _q("work.standup_time", "work", "When is your standup? (HH:MM)",
       "The work brief runner is suggested 30 minutes before it.",
       "10:30", "The work brief suggests 08:30.", "time", when=_domain("work"), when_text="work area enabled"),

    _q("assistants.enabled", "assistants", "Which assistants do you use? (claude, codex, or both)",
       "Setup writes skills and connection config in each assistant's own format.",
       "claude,codex", "Skills are written but no assistant config is created.", "multi",
       choices=["claude", "codex"], default=_detected_assistants),
    _q("assistants.primary", "assistants", "Which assistant should scheduled runs use by default?",
       "Each scheduled run needs one assistant to run without you. You can override per run.",
       "claude", "The first one you picked.", "choice", choices=["claude", "codex"],
       when=lambda a: len(a.get("assistants.enabled") or []) > 1, when_text="both assistants picked"),
]

TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def applies(question, answers):
    when = question.get("when")
    return when is None or bool(when(answers))


def _choice(token, choices):
    token = token.strip().lower()
    if token.isdigit() and 1 <= int(token) <= len(choices):
        return choices[int(token) - 1]
    if token in choices:
        return token
    raise ValueError("Pick from: " + ", ".join(choices) + " (names or numbers).")


def parse(question, raw):
    """Turn typed text (or an answers-file value) into the stored value, or raise ValueError with a hint."""
    kind = question["kind"]
    if isinstance(raw, (list, bool)) and kind in ("multi", "yesno"):
        raw = ",".join(raw) if isinstance(raw, list) else ("yes" if raw else "no")
    text = str(raw).strip()
    if not text:
        raise ValueError("Type an answer, or 'skip'.")
    if kind == "currency":
        if not (len(text) == 3 and text.isascii() and text.isalpha()):
            raise ValueError("Use a three-letter code such as INR or USD.")
        return text.upper()
    if kind == "time":
        if not TIME.match(text):
            raise ValueError("Use 24-hour HH:MM, for example 07:30 or 22:00.")
        return text
    if kind == "number":
        try:
            value = Decimal(text.replace(",", ""))
        except InvalidOperation:
            value = None
        if value is None or not value.is_finite() or value < 0:
            raise ValueError("Use a plain non-negative number, for example 40000.")
        return format(value, "f")
    if kind == "yesno":
        if text.lower() in ("y", "yes", "true"):
            return True
        if text.lower() in ("n", "no", "false"):
            return False
        raise ValueError("Answer yes or no.")
    if kind == "choice":
        return _choice(text, question["choices"])
    if kind == "multi":
        if text.lower() == "none":
            return []
        picked = []
        for token in text.split(","):
            if token.strip():
                value = _choice(token, question["choices"])
                if value not in picked:
                    picked.append(value)
        return picked
    if kind == "timezone":
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(text)
        except ImportError:
            pass
        except Exception:
            raise ValueError("Use a timezone name such as Asia/Kolkata or America/New_York.")
        return text
    if kind == "path":
        return str(Path(text).expanduser())
    return text


def guide_markdown():
    lines = ["# Setup questions, explained", "",
             "<!-- Generated by `python3 -m lifekit guide`; edit lifekit/questions.py instead. -->", "",
             "`life-kit setup` asks these in order and saves each answer as you go, so you can stop",
             "and resume. At any prompt type `skip` to leave it unknown, or `back` to redo the previous",
             "answer. Nothing is sent anywhere while you answer: answers stay in your workspace under",
             "`.local/setup-answers.json`. Secrets (tokens, keys) are typed hidden and stored separately.", ""]
    for section, title, intro in SECTIONS:
        items = [q for q in QUESTIONS if q["section"] == section]
        if not items:
            continue
        lines += ["## " + title, "", intro, ""]
        for q in items:
            lines += ["### " + q["prompt"], "",
                      "- **Why:** " + q["why"],
                      "- **Example:** " + q["example"],
                      "- **If you skip:** " + q["skip"]]
            if q.get("choices"):
                lines.append("- **Choices:** " + ", ".join(q["choices"]))
            if q.get("when_text"):
                lines.append("- **Asked when:** " + q["when_text"])
            if q["kind"] == "secret":
                lines.append("- **Typed hidden** and stored only in your workspace, never in answers or logs.")
            lines.append("")
    return "\n".join(lines)
