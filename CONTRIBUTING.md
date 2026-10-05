# Sharing your setup

## The easy way: the submission form

1. In Windhawk Share, go to the **Export** tab, tick the mods you want to share and click
   **Save package...**.
2. Take 1 to 5 screenshots of your desktop (PNG, JPEG or WebP, up to 3 MB each).
3. Open a new issue with the **Submit a setup** form.
4. Open your `.json` file in Notepad, copy all of its content and paste it into the
   **Setup package (JSON)** field.
5. Drag and drop your screenshots into the **Screenshots** field. The first one is the cover.
6. Submit. An automatic check replies within a few minutes. If something needs fixing, edit the
   issue and the check runs again.

Your setup appears in the gallery once a maintainer approves it.

To update your setup later, submit it again with the same package name. Only you can change
setups you shared.

## Rules

- Only mods from the [official Windhawk repository](https://github.com/ramensoftware/windhawk-mods).
  Windhawk Share already excludes local and modified mods when exporting.
- Screenshots must not show personal information: names, email addresses, file names, notifications.
  Check your taskbar, desktop icons and open windows.
- No inappropriate content.
- Settings that contain file paths (for example a wallpaper in your user folder) are allowed, but
  remember they point to files on your PC that other people won't have.

## Advanced: pull requests

You can also open a pull request that adds a folder `setups/<name>/` with:

- `setup.json`: the package exported by Windhawk Share
- `meta.json`: `{"github": "your-github-username"}`
- `screenshot-1.png` (and optionally `screenshot-2` to `screenshot-5`, PNG, JPEG or WebP)

The folder name uses lowercase letters, digits and hyphens. A pull request may change only one
setup folder and nothing else.
