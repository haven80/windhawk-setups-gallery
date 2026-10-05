"""
Builds the static gallery site into _site/ from the setups/ folder.

Every piece of user-provided text is HTML-escaped. Screenshots are re-encoded,
which also strips any metadata (EXIF, location, camera info) they may contain.

Usage: python scripts/build_site.py
"""

from __future__ import annotations

import html
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate  # noqa: E402

ROOT = validate.ROOT
SETUPS = validate.SETUPS
OUT = ROOT / "_site"
ASSETS = Path(__file__).resolve().parent / "site_assets"

FULL_WIDTH = 1920
THUMB_WIDTH = 760


def e(text: object) -> str:
    return html.escape(str(text), quote=True)


def load_config() -> dict:
    return json.loads((ROOT / "site.config.json").read_text(encoding="utf-8"))


def parse_date(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def process_image(source: Path, full: Path, thumb: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(source) as image:
        image = image.convert("RGBA" if image.mode in ("RGBA", "LA", "P") else "RGB")
        for target, width in ((full, FULL_WIDTH), (thumb, THUMB_WIDTH)):
            copy = image.copy()
            if copy.width > width:
                copy = copy.resize((width, round(copy.height * width / copy.width)), Image.LANCZOS)
            # Saving without exif= drops all metadata.
            copy.save(target, "WEBP", quality=82, method=6)
        return image.width, image.height


def collect() -> list[dict]:
    setups = []
    if not SETUPS.exists():
        return setups
    for folder in sorted(p for p in SETUPS.iterdir() if p.is_dir()):
        # The official check already ran when the setup was accepted.
        result = validate.validate_setup(folder, check_official=False)
        if not result.ok:
            print(f"Skipping {folder.name}: {'; '.join(result.errors)}", file=sys.stderr)
            continue
        package = json.loads((folder / "setup.json").read_text(encoding="utf-8-sig"))
        meta = package["meta"]
        windows = meta.get("windows") or {}
        screenshots = sorted(
            (p for p in folder.iterdir() if validate.SCREENSHOT_RE.match(p.name)),
            key=lambda p: int(validate.SCREENSHOT_RE.match(p.name).group(1)))
        setups.append({
            "slug": folder.name,
            "folder": folder,
            "name": meta.get("name", "").strip(),
            "author": meta.get("author", "").strip(),
            "description": meta.get("description", "").strip(),
            "github": validate.read_owner(folder),
            "created": parse_date(meta.get("createdAt", "")),
            "windows": str(windows.get("product", "")),
            "build": windows.get("build"),
            "windhawk": meta.get("windhawkVersion") or "",
            "mods": [{
                "id": m["id"],
                "version": m.get("version", ""),
                "enabled": m.get("enabled", True),
                "settings": len(m.get("settings", {})),
            } for m in package["mods"]],
            "warnings": result.warnings,
            "screenshots": screenshots,
        })
    setups.sort(key=lambda s: s["created"], reverse=True)
    return setups


def page(config: dict, title: str, body: str, root: str, description: str = "") -> str:
    full_title = e(config["title"]) if title == config["title"] else f"{e(title)} | {e(config['title'])}"
    donate = ""
    if config.get("donateUrl"):
        donate = f'<a href="{e(config["donateUrl"])}" rel="noopener">{e(config.get("donateLabel") or "Donate")}</a>'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{full_title}</title>
<meta name="description" content="{e(description or config['tagline'])}">
<link rel="stylesheet" href="{root}assets/style.css">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🦅</text></svg>">
</head>
<body>
{body}
<footer class="site-footer">
  <p>Not affiliated with Windhawk or RamenSoftware. Mods are installed from the official Windhawk repository.</p>
  <nav>
    <a href="{e(config['repo'])}" rel="noopener">Source on GitHub</a>
    <a href="{e(config['toolDownload'])}" rel="noopener">Get Windhawk Share</a>
    {donate}
  </nav>
</footer>
<script src="{root}assets/app.js" defer></script>
</body>
</html>
"""


def submit_url(config: dict) -> str:
    return config["repo"].rstrip("/") + "/issues/new?template=submit-setup.yml"


def window_frame(inner: str, caption: str) -> str:
    """Screenshots are framed like a Windows 11 window: the one decorative element of the site."""
    return f"""<div class="window">
  <div class="window-bar" aria-hidden="true"><span class="window-title">{e(caption)}</span><span class="window-buttons"><i></i><i></i><i></i></span></div>
  {inner}
</div>"""


def card(s: dict, featured: bool) -> str:
    mod_ids = [m["id"] for m in s["mods"]]
    chips = "".join(f"<li>{e(i)}</li>" for i in mod_ids[:3])
    if len(mod_ids) > 3:
        chips += f'<li class="more">{len(mod_ids) - 3} more</li>'
    search = " ".join([s["name"], s["author"], s["github"] or "", s["description"], *mod_ids]).lower()
    image = f'<img src="s/{e(s["slug"])}/shot-1-thumb.webp" alt="Screenshot of {e(s["name"])}" loading="lazy">'
    by = f'<p class="byline">by {e(s["author"] or s["github"])}</p>'
    return f"""<a class="card{' featured' if featured else ''}" href="s/{e(s['slug'])}/"
   data-search="{e(search)}" data-windows="{e(s['windows'])}" data-mods="{e(' '.join(mod_ids))}">
  {window_frame(image, s['name'])}
  <div class="card-body">
    <h2>{e(s['name'])}</h2>
    {by}
    <ul class="chips">{chips}</ul>
  </div>
</a>"""


def build_index(config: dict, setups: list[dict]) -> str:
    all_mods = sorted({m["id"] for s in setups for m in s["mods"]})
    mod_options = "".join(f'<option value="{e(m)}">{e(m)}</option>' for m in all_mods)
    if setups:
        cards = "\n".join(card(s, i == 0) for i, s in enumerate(setups))
        grid = f"""<section class="controls" aria-label="Filter setups">
  <label class="search"><span class="visually-hidden">Search</span>
    <input type="search" id="q" placeholder="Search by name, author or mod" autocomplete="off"></label>
  <label><span class="visually-hidden">Windows version</span>
    <select id="windows"><option value="">Any Windows</option><option>Windows 11</option><option>Windows 10</option></select></label>
  <label><span class="visually-hidden">Mod</span>
    <select id="mod"><option value="">Any mod</option>{mod_options}</select></label>
</section>
<section class="grid" id="grid">
{cards}
</section>
<p class="empty" id="no-results" hidden>No setups match these filters. Try a different search or clear the filters.</p>"""
    else:
        grid = f"""<section class="empty-state">
  <h2>No setups yet</h2>
  <p>Export your setup with Windhawk Share and be the first to share it.</p>
  <a class="button primary" href="{e(submit_url(config))}" rel="noopener">Submit your setup</a>
</section>"""

    body = f"""<header class="masthead">
  <div class="masthead-text">
    <h1>{e(config['title'])}</h1>
    <p>{e(config['tagline'])}</p>
  </div>
  <div class="actions">
    <a class="button primary" href="{e(submit_url(config))}" rel="noopener">Submit your setup</a>
    <a class="button" href="{e(config['toolDownload'])}" rel="noopener">Get Windhawk Share</a>
  </div>
</header>
<main>
{grid}
</main>"""
    return page(config, config["title"], body, "")


def build_detail(config: dict, s: dict) -> str:
    shots = []
    for i, _ in enumerate(s["screenshots"], start=1):
        lazy = "" if i == 1 else ' loading="lazy"'
        img = f'<a href="shot-{i}.webp"><img src="shot-{i}.webp" alt="Screenshot {i} of {e(s["name"])}"{lazy}></a>'
        shots.append(window_frame(img, s["name"]))

    rows = "".join(
        f"""<tr><td><a href="https://windhawk.net/mods/{e(m['id'])}" rel="noopener">{e(m['id'])}</a></td>
<td>{e(m['version'])}</td><td>{m['settings']}</td><td>{'Enabled' if m['enabled'] else 'Disabled'}</td></tr>"""
        for m in s["mods"])

    warnings = ""
    if s["warnings"]:
        items = "".join(f"<li>{e(w)}</li>" for w in s["warnings"])
        warnings = f"""<aside class="notice">
  <h2>Settings with paths or commands</h2>
  <p>Some settings in this setup contain file paths, commands or web addresses. Windhawk Share shows them again before applying anything.</p>
  <ul>{items}</ul>
</aside>"""

    github = s["github"]
    shared_by = e(s["author"] or github)
    if github:
        shared_by += f' <a href="https://github.com/{e(github)}" rel="noopener">@{e(github)}</a>'
    windows = e(s["windows"]) + (f" (build {e(s['build'])})" if s["build"] else "")
    description = f'<p class="description">{e(s["description"])}</p>' if s["description"] else ""

    body = f"""<header class="detail-header">
  <a class="back" href="../../">All setups</a>
  <h1>{e(s['name'])}</h1>
  <p class="byline">Shared by {shared_by}</p>
  {description}
</header>
<main class="detail">
  <div class="primary">
    <div class="shots">
      {''.join(shots)}
    </div>
    {warnings}
    <section class="mods">
      <h2>Mods in this setup</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Mod</th><th>Version</th><th>Settings</th><th>State</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>
  </div>
  <div class="side">
    <a class="button primary download" href="{e(s['slug'])}.json" download>Download setup</a>
    <dl class="facts">
      <dt>Windows</dt><dd>{windows}</dd>
      <dt>Windhawk</dt><dd>{e(s['windhawk'] or 'Unknown')}</dd>
      <dt>Shared on</dt><dd>{s['created'].strftime('%d %B %Y')}</dd>
      <dt>Mods</dt><dd>{len(s['mods'])}</dd>
    </dl>
    <section class="howto">
      <h2>How to import</h2>
      <ol>
        <li>Download the setup and <a href="{e(config['toolDownload'])}" rel="noopener">Windhawk Share</a>.</li>
        <li>Run Windhawk Share as administrator. It needs Windhawk 2.0 or later.</li>
        <li>On the Import tab, click Open package and choose the file.</li>
        <li>Review the plan, then click Apply.</li>
      </ol>
    </section>
  </div>
</main>"""
    return page(config, s["name"], body, "../../", s["description"][:160])


def main() -> int:
    config = load_config()
    setups = collect()

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "assets").mkdir(parents=True)
    for asset in ASSETS.iterdir():
        shutil.copy(asset, OUT / "assets" / asset.name)
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    index_data = []
    for s in setups:
        target = OUT / "s" / s["slug"]
        target.mkdir(parents=True)
        for i, shot in enumerate(s["screenshots"], start=1):
            process_image(shot, target / f"shot-{i}.webp", target / f"shot-{i}-thumb.webp")
        shutil.copy(s["folder"] / "setup.json", target / f"{s['slug']}.json")
        (target / "index.html").write_text(build_detail(config, s), encoding="utf-8")
        index_data.append({
            "slug": s["slug"], "name": s["name"], "author": s["author"], "github": s["github"],
            "description": s["description"], "createdAt": s["created"].isoformat(),
            "windows": s["windows"], "mods": [m["id"] for m in s["mods"]],
            "package": f"s/{s['slug']}/{s['slug']}.json",
            "thumbnail": f"s/{s['slug']}/shot-1-thumb.webp",
        })

    (OUT / "index.html").write_text(build_index(config, setups), encoding="utf-8")
    # Machine-readable list, for a future "Browse" tab in Windhawk Share.
    (OUT / "index.json").write_text(
        json.dumps({"formatVersion": 1, "setups": index_data}, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Built {len(setups)} setup(s) into {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
