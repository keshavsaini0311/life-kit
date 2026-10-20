"""Install runners with the operating system's own user scheduler. Nothing is installed without a call to install()."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shlex
import subprocess
import sys

from . import core, runners

SOURCE = str(Path(__file__).resolve().parents[1])  # lets `python -m lifekit` work from a source checkout
WEEKDAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
INSTALLED = ".local/runners/installed.json"


def label(root, name):
    return "io.lifekit." + hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()[:8] + "." + name


def set_runner(root, runner_id, times, days="daily", enabled=True, assistant=None):
    """Validate and save a runner's schedule in life.json. `times` is "HH:MM[,HH:MM]"."""
    from .questions import parse
    if runner_id not in runners.RUNNERS:
        raise ValueError("Unknown runner: " + runner_id)
    value = parse({"id": runner_id, "kind": "schedule"}, times + " " + days)

    def change(config):
        entry = config.setdefault("runners", {}).setdefault(runner_id, {})
        entry.update(enabled=enabled, times=value["times"], days=value["days"])
        if assistant:
            entry["assistant"] = assistant
    core.update_config(root, change)


def _env():
    return {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": SOURCE}


def jobs(root, config):
    root = Path(root).resolve()
    base = [sys.executable, "-m", "lifekit", "--workspace", str(root)]
    result = []
    ready = runners.available(config)
    for rid in runners.RUNNERS:
        s = runners.setting(config, rid)
        if s["enabled"] and rid in ready:
            result.append({"runner": rid, "label": label(root, rid), "argv": base + ["run", rid], "times": s["times"],
                           "days": s["days"], "keepalive": False, "title": runners.RUNNERS[rid]["title"], "root": str(root)})
    telegram = config.get("telegram") or {}
    if telegram.get("enabled") and telegram.get("owner"):
        result.append({"runner": "telegram", "label": label(root, "telegram"), "argv": base + ["telegram", "run"],
                       "times": [], "days": "daily", "keepalive": True, "title": "Telegram phone channel", "root": str(root)})
    return result


def _days(days):
    if days == "daily":
        return None
    if days == "weekdays":
        return [1, 2, 3, 4, 5]
    return [WEEKDAYS.index(days)]


def _launchd(job, home):
    data = {"Label": job["label"], "ProgramArguments": job["argv"], "EnvironmentVariables": _env(),
            "WorkingDirectory": job["root"],
            "StandardOutPath": str(Path(job["root"]) / ".local/logs" / (job["runner"] + ".scheduler.log")),
            "StandardErrorPath": str(Path(job["root"]) / ".local/logs" / (job["runner"] + ".scheduler.log"))}
    if job["keepalive"]:
        data.update(KeepAlive=True, RunAtLoad=True)
    else:
        intervals = []
        for t in job["times"]:
            hour, minute = int(t[:2]), int(t[3:])
            days = _days(job["days"])
            intervals += [{"Hour": hour, "Minute": minute}] if days is None else \
                [{"Hour": hour, "Minute": minute, "Weekday": d} for d in days]
        data["StartCalendarInterval"] = intervals
    path = home / "Library/LaunchAgents" / (job["label"] + ".plist")
    domain = "gui/" + str(os.getuid() if hasattr(os, "getuid") else 0)
    return [{"path": path, "content": plistlib.dumps(data).decode()},
            {"command": ["launchctl", "bootout", domain + "/" + job["label"]], "ok_to_fail": True},
            {"command": ["launchctl", "bootstrap", domain, str(path)]}]


def _calendar(job):
    days = {"daily": "", "weekdays": "Mon..Fri "}.get(job["days"], job["days"].title() + " ")
    return ["OnCalendar=" + days + "*-*-* " + t + ":00" for t in job["times"]]


def _systemd(job, home):
    folder = home / ".config/systemd/user"
    env = " ".join('"' + k + "=" + v + '"' for k, v in _env().items())
    service = ["[Unit]", "Description=Life Kit: " + job["title"], "", "[Service]",
               "Type=" + ("simple" if job["keepalive"] else "oneshot"), "Environment=" + env,
               "WorkingDirectory=" + job["root"], "ExecStart=" + " ".join(shlex.quote(a) for a in job["argv"])]
    if job["keepalive"]:
        service += ["Restart=always", "RestartSec=30", "", "[Install]", "WantedBy=default.target"]
        return [{"path": folder / (job["label"] + ".service"), "content": "\n".join(service) + "\n"},
                {"command": ["systemctl", "--user", "daemon-reload"]},
                {"command": ["systemctl", "--user", "enable", "--now", job["label"] + ".service"]}]
    timer = ["[Unit]", "Description=Life Kit schedule: " + job["title"], "", "[Timer]"] + _calendar(job) + \
            ["Persistent=true", "", "[Install]", "WantedBy=timers.target"]
    return [{"path": folder / (job["label"] + ".service"), "content": "\n".join(service) + "\n"},
            {"path": folder / (job["label"] + ".timer"), "content": "\n".join(timer) + "\n"},
            {"command": ["systemctl", "--user", "daemon-reload"]},
            {"command": ["systemctl", "--user", "enable", "--now", job["label"] + ".timer"]}]


def _cron_lines(jobs_):
    env = " ".join(k + "=" + shlex.quote(v) for k, v in _env().items())
    lines = []
    for job in jobs_:
        command = env + " " + " ".join(shlex.quote(a) for a in job["argv"]) + " >/dev/null 2>&1"
        if job["keepalive"]:
            lines.append("@reboot " + command)
            continue
        days = {"daily": "*", "weekdays": "1-5"}.get(job["days"], str(WEEKDAYS.index(job["days"]) if job["days"] in WEEKDAYS else "*"))
        for t in job["times"]:
            lines.append(str(int(t[3:])) + " " + str(int(t[:2])) + " * * " + days + " " + command)
    return lines


def _windows(job, root):
    wrapper = Path(root) / ".local/runners" / (job["runner"] + ".cmd")
    body = "@echo off\r\nset \"PYTHONPATH=" + SOURCE + "\"\r\n" + " ".join('"' + a + '"' for a in job["argv"]) + "\r\n"
    actions = [{"path": wrapper, "content": body}]
    if job["keepalive"]:
        return actions + [{"command": ["schtasks", "/Create", "/F", "/TN", "LifeKit\\" + job["label"], "/SC", "ONLOGON", "/TR", str(wrapper)]}]
    for t in job["times"]:
        name = "LifeKit\\" + job["label"] + "-" + t.replace(":", "")
        days = _days(job["days"])
        schedule_args = ["/SC", "DAILY"] if days is None else ["/SC", "WEEKLY", "/D", ",".join(WEEKDAYS[d].upper() for d in days)]
        actions.append({"command": ["schtasks", "/Create", "/F", "/TN", name] + schedule_args + ["/ST", t, "/TR", str(wrapper)]})
    return actions


def plan(jobs_, platform=sys.platform, home=None, systemd=True):
    home = Path(home or Path.home())
    actions = []
    if platform == "darwin":
        for job in jobs_:
            actions += _launchd(job, home)
    elif platform.startswith("linux") and systemd:
        for job in jobs_:
            actions += _systemd(job, home)
    elif platform.startswith("linux") or platform.startswith("freebsd"):
        actions.append({"cron": _cron_lines(jobs_)})
    elif platform == "win32":
        for job in jobs_:
            actions += _windows(job, job["root"])
    else:
        raise ValueError("No supported scheduler for " + platform + ". Run `life-kit run ID` from your own scheduler.")
    return actions


def _systemd_available(run):
    try:
        return run(["systemctl", "--user", "show-environment"], capture_output=True, text=True).returncode == 0
    except OSError:
        return False


def _cron(root, lines, run, dry_run):
    tag = hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()[:8]
    begin, end = "# BEGIN life-kit " + tag, "# END life-kit " + tag
    current = run(["crontab", "-l"], capture_output=True, text=True)
    text = current.stdout if current.returncode == 0 else ""
    kept, skipping = [], False
    for line in text.splitlines():
        if line == begin:
            skipping = True
        elif line == end:
            skipping = False
        elif not skipping:
            kept.append(line)
    block = [begin] + lines + [end] if lines else []
    new = "\n".join(kept + block) + "\n"
    if not dry_run:
        run(["crontab", "-"], input=new, capture_output=True, text=True)
    return block


def _record(root):
    path = Path(root) / INSTALLED
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def remove(root, run=subprocess.run, platform=sys.platform, home=None, systemd=None, dry_run=False):
    """Remove everything previously installed for this workspace."""
    root = Path(root).resolve()
    home = Path(home or Path.home())
    record = _record(root)
    done = []
    for item in record.get("files", []):
        path = Path(item)
        if path.suffix == ".plist" and not dry_run:
            run(["launchctl", "bootout", "gui/" + str(os.getuid() if hasattr(os, "getuid") else 0) + "/" + path.stem], capture_output=True)
        if path.suffix == ".timer" and not dry_run:
            run(["systemctl", "--user", "disable", "--now", path.name], capture_output=True)
        if path.suffix == ".service" and not dry_run:
            run(["systemctl", "--user", "disable", "--now", path.name], capture_output=True)
        if not dry_run and path.exists():
            path.unlink()
        done.append("removed " + str(path))
    for name in record.get("tasks", []):
        if not dry_run:
            run(["schtasks", "/Delete", "/F", "/TN", name], capture_output=True)
        done.append("removed task " + name)
    if record.get("cron"):
        _cron(root, [], run, dry_run)
        done.append("removed crontab block")
    if not dry_run:
        core.private_write(root / INSTALLED, core.json_text({}))
    return done


def install(root, dry_run=False, run=subprocess.run, platform=sys.platform, home=None, systemd=None):
    """Replace this workspace's scheduled jobs with the enabled runners. Returns a description of each step."""
    root, config = core.load(root)
    home = Path(home or Path.home())
    if platform.startswith("linux") and systemd is None:
        systemd = _systemd_available(run)
    actions = plan(jobs(root, config), platform, home, systemd if systemd is not None else True)
    if not dry_run:
        remove(root, run, platform, home)
    log, record = [], {"files": [], "tasks": [], "cron": False}
    for action in actions:
        if "path" in action:
            log.append("write " + str(action["path"]))
            if not dry_run:
                action["path"].parent.mkdir(parents=True, exist_ok=True)
                action["path"].write_text(action["content"], encoding="utf-8")
            if action["path"].suffix != ".cmd":
                record["files"].append(str(action["path"]))
        elif "cron" in action:
            log += ["crontab: " + line for line in _cron(root, action["cron"], run, dry_run)]
            record["cron"] = bool(action["cron"])
        else:
            log.append("run " + " ".join(action["command"]))
            if action["command"][0] == "schtasks":
                record["tasks"].append(action["command"][action["command"].index("/TN") + 1])
            if not dry_run:
                result = run(action["command"], capture_output=True, text=True)
                if result.returncode and not action.get("ok_to_fail"):
                    raise ValueError("Scheduler command failed: " + " ".join(action["command"][:3]) + " — "
                                     + (result.stderr or "").strip()[:200])
    if not dry_run:
        (root / ".local/logs").mkdir(parents=True, exist_ok=True, mode=0o700)
        core.private_write(root / INSTALLED, core.json_text(record))
    return log


def status(root):
    root, config = core.load(root)
    record = _record(root)
    lines = []
    for rid in runners.RUNNERS:
        s = runners.setting(config, rid)
        if s["enabled"]:
            lines.append(rid + ": " + ",".join(s["times"]) + " " + s["days"])
    installed = len(record.get("files", [])) + len(record.get("tasks", [])) + (1 if record.get("cron") else 0)
    lines.append(("Installed with the system scheduler (" + str(installed) + " entries)." if installed
                  else "Not installed. Run: life-kit schedule install"))
    return lines
