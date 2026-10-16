#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
CREDENTIALS = Path("/root/.config/localmaxxing/credentials.env")
HELPER = Path("/root/.openclaw/agents/main/agent/workshop-skills/localmaxxing/scripts/localmaxxing_api.py")
NAME = "LOCALMAXXING_API_KEY"

def get_key():
    for line in CREDENTIALS.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("export "):
            s = s[7:].lstrip()
        if s.startswith(NAME + "="):
            value = s.split("=", 1)[1].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"\'":
                value = value[1:-1]
            if value:
                return value
    raise RuntimeError("LocalMaxxing key not found in protected credentials file")

if len(sys.argv) != 2 or sys.argv[1] not in ("speed-dry-run", "speed-submit"):
    raise SystemExit("usage: localmaxxing_call.py speed-dry-run|speed-submit")
env = os.environ.copy()
env[NAME] = get_key()
cmd = [sys.executable, str(HELPER), sys.argv[1], "--payload", str(OUT / "payload.json")]
r = subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=120)
(OUT / (sys.argv[1] + ".stdout.json")).write_text(r.stdout)
(OUT / (sys.argv[1] + ".stderr.txt")).write_text(r.stderr)
print("exit", r.returncode, "stdout_bytes", len(r.stdout), "stderr_bytes", len(r.stderr))
try:
    data = json.loads(r.stdout)
except Exception:
    print("response_parse", "failed")
    print("stderr", r.stderr[:1000])
    raise SystemExit(r.returncode or 1)
for key in ("httpStatus", "statusCode", "valid", "verified", "verifiedRun", "verificationIssues", "issues", "runId", "id", "status", "url"):
    if key in data:
        value = data[key]
        if isinstance(value, (str, int, float, bool, list, dict)):
            print(key, json.dumps(value, ensure_ascii=False)[:3000])
for key in ("verification", "run", "data", "result"):
    value = data.get(key)
    if isinstance(value, dict):
        print(key, json.dumps({k:value.get(k) for k in ("id", "status", "verified", "verifiedRun", "verificationIssues", "engineFlags", "quantization", "tokSOut", "tokSPrefill", "tokSTotal", "ttftMs", "peakVramGb") if k in value}, ensure_ascii=False)[:5000])
if r.returncode:
    print("stderr",r.stderr[:1000])
raise SystemExit(r.returncode)
