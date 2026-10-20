"""Narrow publication guard: paths, symlinks and common credentials. Not a full scanner."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FILES = {"README.md", "AGENTS.md", "CONTRIBUTING.md", "SECURITY.md", "LICENSE", "pyproject.toml", ".gitignore"}
DIRECTORIES = {"lifekit", "tests", "scripts", "examples", "docs", ".github"}
PATTERNS = [
    ("home-directory path", re.compile(r"/(?:Users|home)/[A-Za-z0-9_-]+/")),
    ("GitHub token", re.compile(r"gh[pousr]_" + r"[A-Za-z0-9]{20,}")),
    ("private key", re.compile(r"-----BEGIN " + r"(?:RSA |OPENSSH |EC )?PRIVATE KEY-----")),
    ("personal email address", re.compile(r"[A-Za-z0-9._%+-]+@(?!example\.(?:com|org)\b|anthropic\.com\b|users\.noreply\.github\.com\b)[A-Za-z0-9-]+\.[A-Za-z.]{2,}")),
    ("credential assignment", re.compile(r'(?i)(?:access_token|refresh_token|client_secret|bot_token)\s*[=:]\s*[\"\x27][A-Za-z0-9_./+-]{16,}')),
]


def check():
    result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT, capture_output=True)
    if result.returncode:
        print("Run git init before the public-source check.", file=sys.stderr)
        return 1
    failures = []
    paths = sorted(set(p.decode("utf-8") for p in result.stdout.split(b"\0") if p))
    if not paths:
        print("No source files found.", file=sys.stderr)
        return 1
    for name in paths:
        relative = Path(name)
        path = ROOT / relative
        if len(relative.parts) == 1:
            allowed = name in FILES
        else:
            allowed = relative.parts[0] in DIRECTORIES
        if not allowed:
            failures.append(name + ": unexpected publication path")
        if path.is_symlink():
            failures.append(name + ": symlink could reference private data")
            continue
        if not path.is_file():
            failures.append(name + ": missing tracked file")
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            failures.append(name + ": non-text file requires manual review")
            continue
        for label, pattern in PATTERNS:
            if pattern.search(body):
                failures.append(name + ": possible " + label)
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("Publication guard passed for " + str(len(paths)) + " source files. Review staged content too.")
    return 0


if __name__ == "__main__":
    raise SystemExit(check())
