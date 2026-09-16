// Bare-bones partner deck: headline titles + the figures, nothing else.
//
// One slide per partner-facing figure, in story order; the three methodology
// figures (coordination_bounds, diversity_panels, load_timing) are deliberately
// excluded — caveats travel in the slide deck's spoken track and live in
// RUN_LOG.md / docs/figure_plan_timor.md.
//
//   node tools/make_partner_deck.js
//   -> results/figures/timor_partner_deck.pptx
//
// Requires pptxgenjs (npm). Rebuild the PNGs first (tools/plot_*.py) if the
// results changed.
const pptxgen = require("pptxgenjs");
const path = require("path");

const REPO = path.dirname(__dirname);
const FIG = p => path.join(REPO, "results", "figures", p);

const INK = "0B0B0B";
const INK2 = "52514E";
const BLUE = "2A78D6";
const WHITE = "FFFFFF";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.3 x 7.5

// figure px dims -> aspect-correct placement inside a content box
const DIMS = {
  "village_map.png": [2000, 1639],
  "recipe_and_diesel.png": [2520, 1639],
  "cost_stack.png": [2160, 1120],
  "three_regimes.png": [2560, 880],
  "solar_buildout.png": [1920, 1080],
  "village_supply.png": [1839, 1080],
  "cost_vs_co2.png": [1960, 1240],
  "connection_map.png": [1920, 1280],
  "headline_coordination.png": [2080, 1040],
};

function figSlide(title, png) {
  const slide = pres.addSlide();
  slide.background = { color: WHITE };
  slide.addText(title, {
    x: 0.55, y: 0.28, w: 12.2, h: 0.85,
    fontFace: "Calibri", fontSize: 30, bold: true, color: INK,
    align: "left", margin: 0, valign: "middle",
  });
  // content box below the title
  const bx = 0.55, by = 1.25, bw = 12.2, bh = 5.95;
  const [pw, ph] = DIMS[png];
  const ar = pw / ph;
  let w = bw, h = bw / ar;
  if (h > bh) { h = bh; w = bh * ar; }
  slide.addImage({ path: FIG(png), x: bx + (bw - w) / 2, y: by + (bh - h) / 2, w, h });
  return slide;
}

// ---- 1. title slide ----
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  s.addText("Connecting Timor’s 780 Villages to the Grid", {
    x: 0.9, y: 1.7, w: 11.5, h: 1.5, fontFace: "Calibri", fontSize: 44,
    bold: true, color: INK, margin: 0,
  });
  s.addText("What interconnection is worth — and what it does to the village solar programme", {
    x: 0.9, y: 3.05, w: 11.5, h: 0.7, fontFace: "Calibri", fontSize: 20,
    color: INK2, margin: 0,
  });
  const stats = [
    ["780", "villages · 437,000 households"],
    ["356 MW", "village solar under a carbon cap"],
    ["$2.8 M/yr", "saved by wires, carbon-neutral"],
  ];
  stats.forEach(([big, small], i) => {
    const x = 0.9 + i * 4.0;
    s.addText(big, { x, y: 4.6, w: 3.7, h: 0.9, fontFace: "Calibri",
      fontSize: 40, bold: true, color: BLUE, margin: 0 });
    s.addText(small, { x, y: 5.5, w: 3.7, h: 0.8, fontFace: "Calibri",
      fontSize: 14, color: INK2, margin: 0 });
  });
}

// ---- 2-10. figure slides, story order ----
figSlide("780 villages, 437,000 households across West Timor", "village_map.png");
figSlide("One standard kit serves every village — diesel shrinks to a 3% backup", "recipe_and_diesel.png");
figSlide("The islanded programme is mostly a battery purchase", "cost_stack.png");
figSlide("The carbon cap decides what the wires do", "three_regimes.png");
figSlide("With a carbon cap, the wires complete the solar programme", "solar_buildout.png");
figSlide("Who powers the villages under each plan", "village_supply.png");
figSlide("The trade-off: cheaper with coal, or carbon-neutral", "cost_vs_co2.png");
figSlide("Distance decides who connects", "connection_map.png");
figSlide("What coordination is worth", "headline_coordination.png");

pres.writeFile({ fileName: path.join(REPO, "results", "figures", "timor_partner_deck.pptx") })
  .then(f => console.log("written:", f));
