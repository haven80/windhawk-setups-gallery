"""
Turns a "Submit a setup" issue into a setup folder, then validates it.

Input comes from environment variables (never from the command line, so the issue text
can't be interpreted by the shell):
  ISSUE_BODY, ISSUE_AUTHOR

Output:
  - the folder setups/<slug>/
  - submission-report.md   Markdown report to post as a comment
  - submission.env         SLUG=..., OK=true|false   (read by the workflow)
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate  # noqa: E402

ROOT = validate.ROOT
SETUPS = validate.SETUPS

# Screenshots may only be downloaded from GitHub's own attachment hosts.
ATTACHMENT_RE = re.compile(
    r"https://(?:github\.com/user-attachments/assets/[0-9a-fA-F-]{36}"
    r"|user-images\.githubusercontent\.com/\d+/[\w.-]+"
    r"|private-user-images\.githubusercontent\.com/\d+/[\w.-]+(?:\?[\w=&.%-]*)?)")
MAX_DOWNLOAD = validate.MAX_SCREENSHOT_BYTES


def section(body: str, title: str) -> str:
    """Text of an issue-form section ("### Title" followed by the answer)."""
    match = re.search(rf"^###\s+{re.escape(title)}\s*$(.*?)(?=^###\s|\Z)", body, re.M | re.S)
    return match.group(1).strip() if match else ""


def extract_json(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.S)
    return (fenced.group(1) if fenced else text).strip()


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:50].strip("-")


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "windhawk-share-gallery"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise ValueError("larger than 3 MB")
    return data


def choose_slug(name: str, author: str) -> str:
    base = slugify(name) or "setup"
    if len(base) < 2:
        base = f"setup-{base}"
    candidates = [base, slugify(f"{base}-{author}")] + [slugify(f"{base}-{author}-{i}") for i in range(2, 50)]
    for slug in candidates:
        folder = SETUPS / slug
        owner = validate.read_owner(folder) if folder.exists() else None
        # Free, or already owned by the same person (an update of their own setup).
        if not folder.exists() or (owner and owner.lower() == author.lower()):
            return slug
    raise RuntimeError("could not find a free folder name")


def main() -> int:
    body = os.environ.get("ISSUE_BODY", "")
    author = os.environ.get("ISSUE_AUTHOR", "")
    report: list[str] = []
    created: list[Path] = []

    def finish(ok: bool, slug: str = "") -> int:
        if not ok:
            # Never leave a half-built folder behind.
            for folder in created:
                shutil.rmtree(folder, ignore_errors=True)
        Path("submission-report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
        Path("submission.env").write_text(f"SLUG={slug}\nOK={'true' if ok else 'false'}\n", encoding="utf-8")
        print("\n".join(report))
        return 0

    if not validate.GITHUB_USER_RE.match(author):
        report.append("❌ Invalid issue author.")
        return finish(False)

    raw_json = extract_json(section(body, "Setup package (JSON)"))
    try:
        package = json.loads(raw_json)
        name = str(package["meta"]["name"]).strip()
    except (json.JSONDecodeError, KeyError, TypeError):
        report.append("❌ The **Setup package (JSON)** field doesn't contain a valid Windhawk Share package.")
        report.append("")
        report.append("Open the `.json` file you saved with Windhawk Share in Notepad, "
                      "copy all of its content and paste it into that field.")
        return finish(False)

    urls = list(dict.fromkeys(ATTACHMENT_RE.findall(section(body, "Screenshots"))))
    if not urls:
        report.append("❌ No screenshots found. Drag and drop 1 to 5 images into the **Screenshots** field.")
        return finish(False)
    if len(urls) > 5:
        report.append("❌ Too many screenshots: the maximum is 5.")
        return finish(False)

    slug = choose_slug(name, author)
    folder = SETUPS / slug
    if folder.exists():
        shutil.rmtree(folder)  # update of the author's own setup: rebuilt from the issue
    folder.mkdir(parents=True)
    created.append(folder)

    (folder / "setup.json").write_text(json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (folder / "meta.json").write_text(json.dumps({"github": author}, indent=2) + "\n", encoding="utf-8")

    from PIL import Image, UnidentifiedImageError

    for i, url in enumerate(urls, start=1):
        try:
            data = download(url)
            with Image.open(io.BytesIO(data)) as image:
                fmt = image.format
        except (OSError, ValueError, UnidentifiedImageError) as e:
            report.append(f"❌ Screenshot {i} could not be downloaded or read ({e}).")
            return finish(False)
        ext = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}.get(fmt or "")
        if ext is None:
            report.append(f"❌ Screenshot {i} must be a PNG, JPEG or WebP image.")
            return finish(False)
        (folder / f"screenshot-{i}.{ext}").write_bytes(data)

    result = validate.validate_setup(folder)
    report.append(validate.format_result(result))
    if not result.ok:
        report.append("")
        report.append("Edit this issue to fix the problems: the checks will run again automatically.")
    return finish(result.ok, slug if result.ok else "")


if __name__ == "__main__":
    sys.exit(main())
