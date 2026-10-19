import { test } from "node:test";
import assert from "node:assert/strict";
import { applyScheme, colors, currentScheme, darkPalette, font, lightPalette, pendingLabel, pendingTone } from "./theme.ts";

/** WCAG relative luminance contrast of two #RRGGBB colours. */
function contrast(a: string, b: string): number {
  const lum = (hex: string) => {
    const [r, g, bl] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
  };
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

test("the dark palette has exactly the same colours as the light one", () => {
  assert.deepEqual(Object.keys(darkPalette).sort(), Object.keys(lightPalette).sort());
  for (const v of Object.values(darkPalette)) assert.match(v, /^#[0-9A-Fa-f]{6}$/);
});

test("applyScheme switches the shared colours and the text styles built from them", () => {
  applyScheme("dark");
  assert.equal(currentScheme(), "dark");
  assert.equal(colors.surface, darkPalette.surface);
  assert.equal(font.small.color, darkPalette.textMuted);
  applyScheme("light");
  assert.equal(colors.surface, lightPalette.surface);
  assert.equal(font.small.color, lightPalette.textMuted);
});

test("text stays readable on its background in both themes", () => {
  for (const [name, p] of [["light", lightPalette], ["dark", darkPalette]] as const) {
    const pairs: [string, string, string, number][] = [
      ["text on card", p.text, p.surface, 7],
      ["text on screen", p.text, p.surfaceSubtle, 7],
      ["muted text on card", p.textMuted, p.surface, 4.5],
      ["muted text on screen", p.textMuted, p.surfaceSubtle, 4.5],
      ["link on card", p.brand600 === lightPalette.brand600 ? p.brand600 : p.brand700, p.surface, 4.5],
      ["badge: success", p.success, p.successSoft, 4.5],
      ["badge: warning", p.warning, p.warningSoft, 4.5],
      ["badge: danger", p.danger, p.dangerSoft, 4.5],
      ["badge: info", p.brand700, p.brand50, 4.5],
      ["white on a brand button", p.white, p.brand600, 3.5],
    ];
    for (const [what, fg, bg, min] of pairs) assert.ok(contrast(fg, bg) >= min, `${name}: ${what} ${fg} on ${bg} is ${contrast(fg, bg).toFixed(2)}, wanted ${min}`);
  }
});

test("the pending pill gets warmer the longer a store waits, and is readable in both themes", () => {
  for (const scheme of ["light", "dark"] as const) {
    applyScheme(scheme);
    const tones = [0, 1, 2, 3, 5, 9].map((d) => pendingTone(d));
    assert.equal(new Set(tones.slice(0, 4).map((t) => t.bg)).size, 4);          // due today, 1, 2, 3-4 each look different
    for (const t of tones) assert.ok(contrast(t.fg, t.bg) >= 4.5, `${scheme}: ${t.fg} on ${t.bg}`);
    assert.equal(pendingTone(5).bg, pendingTone(9).bg);
  }
  applyScheme("light");
  assert.deepEqual([0, 1, 2, 7].map(pendingLabel), ["Due today", "1 day pending", "2 days pending", "7 days pending"]);
});
