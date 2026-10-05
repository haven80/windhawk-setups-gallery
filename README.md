# Windhawk Setups

A gallery of desktop setups made with Windhawk mods, ready to import with
[Windhawk Share](https://github.com/YOUR-USERNAME/windhawk-share).

> ⚠️ Windhawk Share is alpha software and requires Windhawk 2.0 or later.

Not affiliated with Windhawk or RamenSoftware.

## How it works

- Each setup is a folder in `setups/<name>/` with the package (`setup.json`), the submitter's GitHub
  username (`meta.json`) and 1 to 5 screenshots.
- People submit setups by filling in the **Submit a setup** issue form. A GitHub Action checks the
  package, builds the setup folder and opens a pull request. Nothing is published until a
  maintainer merges it.
- On every push to `main`, the site is rebuilt and published on GitHub Pages.
- The site is fully static: no server, no database, no cookies, no third-party requests.

Setups follow the same rules as Windhawk Share: only mods from the official Windhawk repository,
no local mods, no code. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Setting up the repository (maintainers)

1. Create a **public** repository and upload these files, including the `.github` folder.
2. Edit `site.config.json`: set `repo`, `toolDownload`, your GitHub username in `maintainers`,
   and optionally `donateUrl` (Ko-fi, GitHub Sponsors, Buy Me a Coffee, Liberapay...).
3. **Settings → Pages**: under *Build and deployment*, set *Source* to **GitHub Actions**.
4. **Settings → Actions → General**: under *Workflow permissions*, tick
   **Allow GitHub Actions to create and approve pull requests**.
5. **Issues → Labels**: create a label named exactly `submission`.
6. Run the **Publish gallery** workflow once (Actions tab → Publish gallery → Run workflow).
   The site appears at `https://YOUR-USERNAME.github.io/YOUR-GALLERY-REPO/`.

## Reviewing submissions

Each submission becomes a pull request with the check results in its description.

- ✅ means the package passed every automatic check.
- ⚠️ lists settings that contain file paths, commands or web addresses. Look at them before merging:
  they're usually harmless (a wallpaper path, for example), but they're the place where something
  odd would show up.
- Look at the screenshots: reject anything inappropriate or showing personal information.
- **Never merge a pull request that changes files outside `setups/`** (workflows, scripts, config)
  unless you wrote it yourself. The validation workflow flags these, but a pull request can also
  modify workflow files, so this rule is the real safeguard.

After merging, close the related issue. The site updates within a couple of minutes.

To remove a setup, delete its folder on `main`.

## Building locally

```
pip install -r scripts/requirements.txt
python scripts/validate.py --all
python scripts/build_site.py
python -m http.server --directory _site
```

## Files

- `setups/`: the setups
- `scripts/validate.py`: the checks (same rules as Windhawk Share's importer)
- `scripts/submission.py`: turns a submission issue into a setup folder
- `scripts/build_site.py`: builds the static site into `_site/`
- `scripts/site_assets/`: the site's CSS and JavaScript
- `.github/ISSUE_TEMPLATE/submit-setup.yml`: the submission form
- `.github/workflows/`: submission processing, pull request validation, site publishing

The site also publishes `index.json`, a machine-readable list of all setups.
