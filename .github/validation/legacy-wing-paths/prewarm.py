"""Fetch Chroma's pinned public model once, without credentials or API calls."""

import hashlib
import json
import os
import sysconfig
import tarfile
import time
import urllib.request
from pathlib import Path, PurePosixPath

home = Path(os.environ["MEM_VALIDATION_HOME"]).resolve()
cache = home / ".cache/chroma/onnx_models/all-MiniLM-L6-v2"
cache.mkdir(parents=True, exist_ok=True)
archive = cache / "onnx.tar.gz"
url = "https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz"
expected = "913d7300ceae3b2dbc2c50d1de4baacab4be7b9380491c27fab7418616a16ec3"
module = (
    Path(sysconfig.get_paths()["purelib"])
    / "chromadb/utils/embedding_functions/onnx_mini_lm_l6_v2.py"
)
if f'_MODEL_SHA256 = "{expected}"' not in module.read_text(encoding="utf-8"):
    raise ValueError("installed Chroma's model pin differs from the reviewed archive")


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


if not archive.exists() or digest(archive) != expected:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    temporary = cache / "onnx.tar.gz.download"
    for attempt in range(3):
        started = time.monotonic()
        try:
            size = 0
            with opener.open(url, timeout=30) as response, temporary.open("wb") as target:
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > 90_000_000 or time.monotonic() - started > 240:
                        raise ValueError("model download exceeded the explicit size/time bound")
                    target.write(chunk)
            if digest(temporary) != expected:
                raise ValueError("Chroma model SHA256 mismatch")
            temporary.replace(archive)
            break
        except OSError:
            if attempt == 2:
                raise
            time.sleep(1)

with tarfile.open(archive, "r:gz") as handle:
    members = handle.getmembers()
    if len(members) > 40 or sum(m.size for m in members) > 200_000_000:
        raise ValueError("model archive inventory exceeds its bound")
    seen = set()
    for member in members:
        name = PurePosixPath(member.name)
        if (
            name.is_absolute()
            or ".." in name.parts
            or not name.parts
            or name.parts[0] != "onnx"
            or "\\" in member.name
            or ":" in member.name
            or not (member.isfile() or member.isdir())
        ):
            raise ValueError(f"unsafe model archive member: {member.name!r}")
        identity = str(name).casefold()
        if identity in seen:
            raise ValueError(f"duplicate model archive member: {member.name!r}")
        seen.add(identity)
    handle.extractall(cache, members=members, filter="data")

print(
    json.dumps(
        {
            "url": url,
            "sha256": digest(archive),
            "compressed_bytes": archive.stat().st_size,
            "members": [{"name": m.name, "bytes": m.size} for m in members],
            "license_reference": "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2",
        }
    ),
    flush=True,
)
