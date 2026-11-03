"""Verify the reviewed source snapshot, then run the project CI command offline."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
repo = here.parents[2]
manifest = json.loads((here / "source-sha256.json").read_text(encoding="utf-8"))
for name, expected in manifest["files"].items():
    data = (repo / name).read_bytes().replace(b"\r\n", b"\n")
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected["lf_sha256"]:
        raise ValueError(f"reviewed source hash mismatch: {name}")
print("Verified six reviewed source/test hashes", flush=True)

home = Path(os.environ["MEM_VALIDATION_HOME"]).resolve()
env = os.environ.copy()
for name in list(env):
    upper = name.upper()
    if (
        upper.startswith(("MEMPALACE_", "MEMPAL_"))
        or upper.endswith(("_API_KEY", "_TOKEN", "_PROXY"))
        or upper in ("OPENAI_BASE_URL", "ANTHROPIC_BASE_URL", "PYTHONPATH")
    ):
        env.pop(name, None)
env.update(
    {
        "HOME": str(home),
        "USERPROFILE": str(home),
        "PYTHONPATH": str(here / "guard"),
        "NO_PROXY": "*",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "ANONYMIZED_TELEMETRY": "False",
        "DO_NOT_TRACK": "1",
        "PYTHONUNBUFFERED": "1",
    }
)
args = [
    sys.executable,
    "-m",
    "pytest",
    "tests/",
    "-v",
    "--ignore=tests/benchmarks",
    "--cov=mempalace",
    "--cov-report=term-missing",
    "--durations=10",
    "--tb=short",
    "--basetemp=" + str(home.parent / "mempalace-pytest"),
]
raise SystemExit(subprocess.run(args, cwd=repo, env=env).returncode)
