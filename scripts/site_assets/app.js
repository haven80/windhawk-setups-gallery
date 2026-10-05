// Client-side filtering of the gallery. Reads only data-* attributes, never inserts HTML.
(function () {
  const grid = document.getElementById("grid");
  if (!grid) return;

  const q = document.getElementById("q");
  const windows = document.getElementById("windows");
  const mod = document.getElementById("mod");
  const noResults = document.getElementById("no-results");
  const cards = Array.from(grid.querySelectorAll(".card"));

  function apply() {
    const terms = q.value.toLowerCase().split(/\s+/).filter(Boolean);
    const win = windows.value;
    const m = mod.value;
    let visible = 0;

    for (const card of cards) {
      const text = card.dataset.search || "";
      const mods = (card.dataset.mods || "").split(" ");
      const show =
        terms.every((t) => text.includes(t)) &&
        (!win || card.dataset.windows === win) &&
        (!m || mods.includes(m));
      card.hidden = !show;
      if (show) visible++;
    }
    // The featured layout only makes sense on the unfiltered gallery.
    const filtered = terms.length > 0 || win || m;
    grid.classList.toggle("filtered", Boolean(filtered));
    noResults.hidden = visible > 0;
  }

  q.addEventListener("input", apply);
  windows.addEventListener("change", apply);
  mod.addEventListener("change", apply);
})();
