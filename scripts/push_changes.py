import subprocess
import sys
import os

os.chdir(r"e:\AI\Codex\LifeOS\M2news")

print("Staging files...")
subprocess.run(["git", "add", "-A"], check=True)

print("Committing...")
subprocess.run(["git", "commit", "-m", "feat: chief editor mode - LLM prompts, HTML stripping, max 5 per section"], check=False)

print("Pushing to GitHub...")
result = subprocess.run(["git", "push", "origin", "main"], capture_output=True, text=True)
print("stdout:", result.stdout)
print("stderr:", result.stderr)
print("Return code:", result.returncode)
