import subprocess
import sys

cwd = r'e:\AI\Codex\LifeOS\M2news'
result_file = r'e:\AI\Codex\LifeOS\M2news\logs\git_push_result.txt'

commands = [
    ['git', 'add', 'pyproject.toml', '.github/workflows/daily-news.yml'],
    ['git', 'commit', '-m', 'fix: correct pyproject.toml build-backend to setuptools.build_meta'],
    ['git', 'push', 'origin', 'main'],
]

output = []
for cmd in commands:
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=30)
    output.append(f"CMD: {' '.join(cmd)}")
    output.append(f"RC: {r.returncode}")
    if r.stdout:
        output.append(f"STDOUT: {r.stdout}")
    if r.stderr:
        output.append(f"STDERR: {r.stderr}")
    output.append("")

with open(result_file, 'w', encoding='utf-8') as f:
    f.write('\n'.join(output))

print('\n'.join(output))
