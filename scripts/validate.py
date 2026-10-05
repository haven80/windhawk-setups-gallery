"""
Validates gallery setups with the same rules Windhawk Share uses on import.

A setup is a folder setups/<slug>/ containing exactly:
  setup.json         the package exported by Windhawk Share
  meta.json          {"github": "<submitter's GitHub username>"}
  screenshot-N.ext   1 to 5 screenshots (png, jpg, jpeg, webp), N = 1..5

Usage:
  python scripts/validate.py --all                       validate every setup
  python scripts/validate.py --pr <base-sha> <author>     validate the setups changed by a pull request
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETUPS = ROOT / "setups"

# The official repository is hard-coded and never read from submitted files.
OFFICIAL_RAW_BASE = "https://raw.githubusercontent.com/ramensoftware/windhawk-mods/main/mods/"

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
MOD_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+-]{0,31}$")
SETTING_KEY_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\[\]$-]{0,255}$")
GITHUB_USER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
SCREENSHOT_RE = re.compile(r"^screenshot-([1-5])\.(png|jpg|jpeg|webp)$")

MAX_PACKAGE_BYTES = 1 * 1024 * 1024
MAX_SCREENSHOT_BYTES = 3 * 1024 * 1024
MAX_IMAGE_SIDE = 8000
MAX_MODS = 200
MAX_SETTINGS_PER_MOD = 5000
MAX_STRING_VALUE = 64 * 1024
MAX_TEXT = {"name": 80, "author": 60, "description": 1000}

SUSPICIOUS = (":\\", "\\\\", "%", "http://", "https://", ".exe", ".ps1", ".bat", ".cmd")


@dataclass
class Result:
    slug: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


_official_cache: dict[str, bool] = {}


def is_official_mod(mod_id: str) -> bool:
    """True if the mod exists in the official repository. Raises on network errors."""
    if mod_id not in _official_cache:
        request = urllib.request.Request(
            OFFICIAL_RAW_BASE + mod_id + ".wh.cpp",
            method="HEAD",
            headers={"User-Agent": "windhawk-share-gallery"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                _official_cache[mod_id] = response.status == 200
        except urllib.error.HTTPError as e:
            if e.code == 404:
                _official_cache[mod_id] = False
            else:
                raise
    return _official_cache[mod_id]


def looks_like_path_or_command(value: str) -> bool:
    lower = value.lower()
    return any(s in lower for s in SUSPICIOUS)


def validate_package(package_path: Path, result: Result, check_official: bool) -> dict | None:
    if package_path.stat().st_size > MAX_PACKAGE_BYTES:
        result.errors.append("setup.json is larger than 1 MB.")
        return None
    try:
        package = json.loads(package_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        result.errors.append(f"setup.json is not valid JSON: {e}")
        return None

    if not isinstance(package, dict) or package.get("formatVersion") != 1:
        result.errors.append("setup.json is not a Windhawk Share package (formatVersion must be 1).")
        return None

    meta = package.get("meta")
    if not isinstance(meta, dict):
        result.errors.append("setup.json has no 'meta' section.")
        return None
    for key, limit in MAX_TEXT.items():
        value = meta.get(key, "")
        if not isinstance(value, str):
            result.errors.append(f"meta.{key} must be text.")
        elif len(value) > limit:
            result.errors.append(f"meta.{key} is longer than {limit} characters.")
    if not str(meta.get("name", "")).strip():
        result.errors.append("The package has no name.")

    mods = package.get("mods")
    if not isinstance(mods, list) or not mods:
        result.errors.append("The package contains no mods.")
        return None
    if len(mods) > MAX_MODS:
        result.errors.append(f"The package contains more than {MAX_MODS} mods.")
        return None

    seen: set[str] = set()
    for mod in mods:
        if not isinstance(mod, dict):
            result.errors.append("Invalid mod entry.")
            continue
        mod_id = mod.get("id")
        if not isinstance(mod_id, str) or not MOD_ID_RE.match(mod_id):
            result.errors.append(f"Invalid mod ID or local mod: {str(mod_id)[:60]!r}.")
            continue
        if mod_id in seen:
            result.errors.append(f"Mod '{mod_id}' is listed twice.")
            continue
        seen.add(mod_id)

        version = mod.get("version")
        if not isinstance(version, str) or not VERSION_RE.match(version):
            result.errors.append(f"{mod_id}: invalid version.")

        if check_official:
            try:
                if not is_official_mod(mod_id):
                    result.errors.append(f"{mod_id}: not in the official Windhawk mods repository.")
            except (urllib.error.URLError, TimeoutError) as e:
                result.errors.append(f"{mod_id}: could not check the official repository ({e}).")

        settings = mod.get("settings", {})
        if not isinstance(settings, dict):
            result.errors.append(f"{mod_id}: 'settings' must be an object.")
            continue
        if len(settings) > MAX_SETTINGS_PER_MOD:
            result.errors.append(f"{mod_id}: too many settings.")
            continue
        for key, value in settings.items():
            if not SETTING_KEY_RE.match(key):
                result.errors.append(f"{mod_id}: invalid setting key {key[:60]!r}.")
            elif isinstance(value, bool):
                pass
            elif isinstance(value, int):
                pass
            elif isinstance(value, str):
                if len(value) > MAX_STRING_VALUE:
                    result.errors.append(f"{mod_id}: value of '{key}' is too long.")
                elif any(ord(c) < 32 and c not in "\t\n\r" for c in value):
                    result.errors.append(f"{mod_id}: value of '{key}' contains control characters.")
                elif looks_like_path_or_command(value):
                    shown = value if len(value) <= 120 else value[:120] + "..."
                    result.warnings.append(f"{mod_id}: '{key}' contains a path or command: {shown}")
            else:
                result.errors.append(f"{mod_id}: unsupported value type for '{key}'.")

    return package


def validate_screenshot(path: Path, result: Result) -> None:
    from PIL import Image, UnidentifiedImageError

    if path.stat().st_size > MAX_SCREENSHOT_BYTES:
        result.errors.append(f"{path.name} is larger than 3 MB.")
        return
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            if image.format not in ("PNG", "JPEG", "WEBP"):
                result.errors.append(f"{path.name} is not a PNG, JPEG or WebP image.")
            elif max(image.size) > MAX_IMAGE_SIDE:
                result.errors.append(f"{path.name} is too large ({image.size[0]}x{image.size[1]}).")
    except (UnidentifiedImageError, OSError, SyntaxError) as e:
        result.errors.append(f"{path.name} is not a valid image ({e}).")


def validate_setup(folder: Path, check_official: bool = True) -> Result:
    result = Result(folder.name)

    if not SLUG_RE.match(folder.name):
        result.errors.append(
            f"Folder name '{folder.name}' is invalid: use 2-64 lowercase letters, digits and hyphens.")
        return result

    files = [p for p in folder.iterdir()]
    screenshots = []
    for p in files:
        if p.is_dir() or p.is_symlink():
            result.errors.append(f"'{p.name}' is not allowed (no subfolders or links).")
        elif p.name in ("setup.json", "meta.json"):
            continue
        elif SCREENSHOT_RE.match(p.name):
            screenshots.append(p)
        else:
            result.errors.append(f"'{p.name}' is not allowed in a setup folder.")

    package_path = folder / "setup.json"
    if not package_path.is_file():
        result.errors.append("setup.json is missing.")
    else:
        validate_package(package_path, result, check_official)

    meta_path = folder / "meta.json"
    if not meta_path.is_file():
        result.errors.append("meta.json is missing.")
    else:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if not isinstance(meta, dict) or not GITHUB_USER_RE.match(str(meta.get("github", ""))):
                result.errors.append("meta.json must contain a valid 'github' username.")
        except json.JSONDecodeError as e:
            result.errors.append(f"meta.json is not valid JSON: {e}")

    if not screenshots:
        result.errors.append("At least one screenshot is required (screenshot-1.png).")
    numbers = sorted(int(SCREENSHOT_RE.match(p.name).group(1)) for p in screenshots)
    if len(numbers) != len(set(numbers)):
        result.errors.append("Two screenshots have the same number.")
    for p in screenshots:
        validate_screenshot(p, result)

    return result


def read_owner(folder: Path) -> str | None:
    try:
        return json.loads((folder / "meta.json").read_text(encoding="utf-8")).get("github")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None


def owner_at_revision(revision: str, slug: str) -> str | None:
    """Owner of a setup as it was in another revision (e.g. the base of a pull request)."""
    proc = subprocess.run(
        ["git", "show", f"{revision}:setups/{slug}/meta.json"],
        cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout).get("github")
    except (json.JSONDecodeError, AttributeError):
        return None


def load_maintainers() -> set[str]:
    try:
        config = json.loads((ROOT / "site.config.json").read_text(encoding="utf-8"))
        return {m.lower() for m in config.get("maintainers", [])}
    except (OSError, json.JSONDecodeError):
        return set()


def validate_pull_request(base: str, author: str) -> tuple[bool, str]:
    """Checks a pull request: only one setup folder touched, ownership respected, contents valid."""
    changed = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()

    lines: list[str] = []
    outside = [f for f in changed if not f.startswith("setups/") or f.count("/") != 2]
    if outside:
        lines.append("❌ This pull request changes files outside a setup folder:")
        lines += [f"- `{f}`" for f in outside[:20]]
        lines.append("")
        lines.append("Setup submissions may only add or change files in `setups/<name>/`.")
        return False, "\n".join(lines)

    slugs = sorted({f.split("/")[1] for f in changed})
    if len(slugs) != 1:
        return False, "❌ A pull request must change exactly one setup folder."
    slug = slugs[0]
    folder = SETUPS / slug

    is_maintainer = author.lower() in load_maintainers()
    previous_owner = owner_at_revision(base, slug)
    if previous_owner and previous_owner.lower() != author.lower() and not is_maintainer:
        return False, f"❌ The setup `{slug}` belongs to @{previous_owner}: only they can change it."

    if not folder.exists():
        return True, f"✅ The setup `{slug}` is removed by this pull request."

    current_owner = read_owner(folder)
    if not previous_owner and current_owner and current_owner.lower() != author.lower() and not is_maintainer:
        return False, f"❌ meta.json must contain your own GitHub username (@{author})."

    result = validate_setup(folder)
    return result.ok, format_result(result)


def format_result(result: Result) -> str:
    lines = [f"### Setup `{result.slug}`", ""]
    if result.ok:
        lines.append("✅ All checks passed.")
    else:
        lines.append("❌ Some checks failed:")
        lines += [f"- {e}" for e in result.errors]
    if result.warnings:
        lines += ["", "⚠️ Please review these settings before approving:"]
        lines += [f"- {w}" for w in result.warnings]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true")
    group.add_argument("--pr", nargs=2, metavar=("BASE", "AUTHOR"))
    parser.add_argument("--report", help="write a Markdown report to this file")
    args = parser.parse_args()

    if args.all:
        results = [validate_setup(f) for f in sorted(SETUPS.iterdir()) if f.is_dir()]
        report = "\n\n".join(format_result(r) for r in results) or "No setups yet."
        ok = all(r.ok for r in results)
    else:
        ok, report = validate_pull_request(*args.pr)

    print(report)
    if args.report:
        Path(args.report).write_text(report + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
