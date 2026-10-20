"""Fictional demo. Run: python -m examples.demo"""
from pathlib import Path
import tempfile
from lifekit import core

with tempfile.TemporaryDirectory(prefix="life-kit-demo-") as directory:
    root = core.init(Path(directory) / "workspace", "USD")
    core.checkin(root, sleep=7, gym="rest", prep=25)
    core.spend(root, "12.50", "food", "Fictional demo")
    activity = core.action(root, "learning", "practice", "SQL joins", "worked-example")
    core.outcome(root, activity["id"], "completed", "Fictional self-report")
    print(core.report(root).read_text())
