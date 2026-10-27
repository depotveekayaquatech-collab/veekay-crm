import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AverageCards } from "@/features/capping/AverageCards";
import { ReduceCappingBanner } from "@/features/capping/ReduceCappingBanner";
import { LiveStoresExplorer } from "@/features/inventory/LiveStoresExplorer";
import type { CapSummary } from "@/services/capping";

const row = (o: object = {}) => ({
  storeId: "s1", outletId: "Z-1", outletName: "Store One", state: "Delhi", city: "New Delhi", average: 12.5, cappingAverage: 11.5, cappingDays: 5,
  entryDays: 2, total: 25, maxDay: 13, currentCapping: 11, breachDays: [{ date: "2026-10-02", value: 13 }], alert: true, reasons: ["average", "day"],
  averageBreach: true, cappingBreach: true, dayBreach: true, status: "over", ...o,
});
const overall = { entryAverage: 12.34, entryDays: 10, total: 123, cappingAverage: 11.5, cappingDays: 10, entryBreach: true, cappingBreach: true, alert: true, reasons: ["average", "capping"], status: "over" };
const summary = (o: object = {}) => ({ from: "2026-10-01", to: "2026-10-31", today: "2026-10-27", limit: 11, amberMargin: 1, totals: { stores: 1, inAlert: 1 }, overall, rows: [row()], ...o }) as unknown as CapSummary;
const cards = (s: CapSummary | undefined) => renderToString(createElement(AverageCards, { summary: s, isLoading: false, error: null, onRetry: () => {} }));

describe("capping page pieces never crash on what the API can send", () => {
  it("renders the current payload: collective cards, banner and store cards with two decimals", () => {
    const html = cards(summary()) + renderToString(createElement(ReduceCappingBanner, { summary: summary() }));
    expect(html).toContain("12.34");
    expect(html).toContain("Reduce capping");
    expect(html).not.toContain("Store One");                  // the store-by-store cards are hidden until Expand is clicked
    expect(html).toContain("Expand");
  });
  it("renders an API that has no collective figures yet (web newer than the API)", () => {
    const old = summary({ overall: undefined });
    expect(() => cards(old)).not.toThrow();
    expect(renderToString(createElement(ReduceCappingBanner, { summary: old }))).toBe("");
  });
  it("renders rows with missing capping fields, and no data at all", () => {
    expect(() => cards(summary({ rows: [row({ cappingAverage: undefined, average: undefined, currentCapping: undefined, status: "none" })] }))).not.toThrow();
    expect(() => cards(undefined)).not.toThrow();
    expect(() => cards(summary({ rows: [] }))).not.toThrow();
  });
  it("shows no banner when the collective averages are within the limit", () => {
    expect(renderToString(createElement(ReduceCappingBanner, { summary: summary({ overall: { ...overall, alert: false, entryBreach: false, cappingBreach: false } }) }))).toBe("");
  });
});

describe("Live stores in depth renders", () => {
  const item = (o: object = {}) => ({ platformSlug: "zepto", platform: "Zepto", status: "LIVE", regionName: null, state: "Delhi", city: "Rohini", vendorName: "V", pendingDays: 1, markedToday: false, monthBottles: 4, ...o });
  const render = (items: object[]) => renderToString(createElement(LiveStoresExplorer, { items: items as never, filterActive: false, isPicked: () => false, onPick: () => {}, onClear: () => {} }));
  it("shows live stores and vendors, for both platforms", () => {
    const html = render([item(), item({ vendorName: "W" }), item({ platformSlug: "blinkit", platform: "Blinkit", regionName: "North" })]);
    expect(html).toContain("Live stores in depth");
    expect(html).toContain("Zepto");
    expect(html).toContain("Blinkit");
  });
  it("copes with nothing live", () => {
    expect(() => render([])).not.toThrow();
    expect(() => render([item({ status: "CLOSE" }), item({ state: null, city: null, vendorName: null })])).not.toThrow();
  });
});
