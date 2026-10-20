"""Fictional demo in a temporary folder. Run: python -m examples.demo"""
from pathlib import Path
import tempfile
from lifekit import core

with tempfile.TemporaryDirectory(prefix="life-kit-demo-") as directory:
    root = core.init(Path(directory) / "workspace", "USD")
    core.checkin(root, sleep=7, gym="rest", prep=25)
    core.spend(root, "12.50", "food", "Fictional demo")
    action = core.action(root, "career", "email", "fictional-role", "specific-role")
    core.outcome(root, action["id"], "reply", "Fictional self-report")
    print(core.report(root).read_text())
