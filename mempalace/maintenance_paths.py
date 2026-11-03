"""Maintenance filenames for exact, possibly legacy, stored wing identities."""

import hashlib
import json
import os
import re
import stat

from .config import MempalaceConfig, sanitize_name
from .fsio import open_source_file

_FAMILIES = {
    "split": ("wings", "split-", (".json", ".pending")),
    "rooms": ("rooms", "", (".json", ".apply-pending.json")),
}


def wing_artifact_path(config: MempalaceConfig, wing: str, family: str, suffix: str) -> str:
    """Keep valid filenames; encode legacy keys without changing their identity.

    A safe historical raw filename wins for the *whole* plan/marker family.
    Never hide an interrupted operation by creating its partner under a new
    name. If old and encoded state both exist, leave both for owner review.
    """
    folder, prefix, suffixes = _FAMILIES[family]
    if suffix not in suffixes:
        raise ValueError("unknown maintenance artifact suffix")
    directory = os.path.join(config.palace_path, folder)
    if not isinstance(wing, str) or not wing.strip() or "\x00" in wing:
        raise ValueError("wing must be a non-empty string without null bytes")
    try:
        name = sanitize_name(wing, "wing")
    except ValueError:
        name = "_legacy_" + hashlib.sha256(wing.encode("utf-8", errors="surrogatepass")).hexdigest()
    else:
        return os.path.join(directory, f"{prefix}{name}{suffix}")

    # Existing valid names keep their old behavior. Newly supported legacy
    # paths must not follow a state-directory or artifact symlink on reads.
    def redirected(info):
        return stat.S_ISLNK(info.st_mode) or bool(
            getattr(info, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        )

    try:
        directory_info = os.lstat(directory)
    except FileNotFoundError:
        pass
    else:
        if redirected(directory_info):
            raise ValueError(
                f"maintenance state directory is a symlink or reparse point: {directory}"
            )

    def existing(component):
        found = False
        for extension in suffixes:
            candidate = os.path.join(directory, f"{prefix}{component}{extension}")
            try:
                info = os.lstat(candidate)
            except FileNotFoundError:
                continue
            if redirected(info) or not stat.S_ISREG(info.st_mode):
                raise ValueError(
                    f"maintenance artifact is not a regular file (possibly symlink): {candidate}"
                )
            found = True
        return found

    encoded_exists = existing(name)
    # Only inspect raw names that are portable leaf components, never a path
    # or Windows alternate stream. Long names cannot have portable artifacts.
    safe_raw = (
        re.fullmatch(r"[\w .'-]+", wing) is not None
        and ".." not in wing
        and len((prefix + wing + max(suffixes, key=len)).encode("utf-8")) <= 240
    )
    raw_exists = existing(wing) if safe_raw else False
    if encoded_exists and raw_exists:
        raise ValueError(f"both raw and encoded maintenance artifacts exist for wing {wing!r}")
    if raw_exists:
        name = wing
    # A historical raw name can resemble a reserved digest, and a
    # case-insensitive filesystem can alias two raw spellings. Never let
    # filename equality authorize overwriting another wing's approved plan.
    plan_path = os.path.join(directory, f"{prefix}{name}.json")
    owned_plan = False
    try:
        fd, _ = open_source_file(plan_path)
    except FileNotFoundError:
        pass
    else:
        with os.fdopen(fd, encoding="utf-8") as handle:
            plan = json.load(handle)
        if not isinstance(plan, dict) or plan.get("wing") != wing:
            raise ValueError(f"maintenance artifact at {plan_path} is not for wing {wing!r}")
        owned_plan = True
    marker_path = os.path.join(directory, f"{prefix}{name}{suffixes[-1]}")
    try:
        fd, _ = open_source_file(marker_path)
    except FileNotFoundError:
        pass
    else:
        with os.fdopen(fd, encoding="utf-8") as handle:
            if family == "rooms":
                marker = json.load(handle)
                if not isinstance(marker, dict) or marker.get("wing") != wing:
                    raise ValueError(
                        f"pending room apply at {marker_path} is not for wing {wing!r}"
                    )
            elif not owned_plan:
                # Old split markers identify only a plan fingerprint, not a
                # wing. An orphan must not authorize a fresh plan or deletion.
                raise ValueError(f"split marker at {marker_path} has no owned accompanying plan")
    return os.path.join(directory, f"{prefix}{name}{suffix}")
