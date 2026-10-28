"""Enable the NightRider pre-commit value checkpoint for a local git clone."""
from pathlib import Path
import os
import subprocess

root = Path(__file__).resolve().parent.parent
hook = root / ".githooks" / "commit-msg"
template = root / ".gitmessage"
if not (root / ".git").exists():
    raise SystemExit("Run inside a local Git checkout of NightRider.")
if not hook.is_file() or not template.is_file():
    raise SystemExit("NightRider commit policy files are missing.")
hook.chmod(hook.stat().st_mode | 0o111)
subprocess.run(["git", "-C", str(root), "config", "core.hooksPath", ".githooks"], check=True)
subprocess.run(["git", "-C", str(root), "config", "commit.template", ".gitmessage"], check=True)
print("NightRider pre-commit gate enabled in this clone.")
print("Every git commit now asks the 3 NR questions and checks NR-Value: in the message.")
print("The PR workflow also checks commits made through GitHub tools or other machines.")
