import subprocess
import os

os.chdir(r"e:\AI\Codex\LifeOS\M2news")

print("=== git status ===")
r = subprocess.run(["git", "status", "--short"], capture_output=True, text=True)
print(r.stdout)
print(r.stderr)

print("\n=== git log -3 ===")
r = subprocess.run(["git", "log", "--oneline", "-3"], capture_output=True, text=True)
print(r.stdout)
print(r.stderr)

print("\n=== git diff HEAD -1 --stat ===")
r = subprocess.run(["git", "diff", "HEAD", "--stat"], capture_output=True, text=True)
print(r.stdout[:500])
