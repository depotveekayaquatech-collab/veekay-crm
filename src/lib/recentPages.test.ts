import { describe, expect, it } from "vitest";
import { MAX_RECENT, readRecent, rememberRecent } from "./recentPages";

const memory = () => {
  const data = new Map<string, string>();
  return { getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => void data.set(k, v) };
};

describe("recent pages", () => {
  it("remembers the newest first and never lists a page twice", () => {
    const s = memory();
    rememberRecent("k", { label: "Stores", to: "/stores" }, s);
    rememberRecent("k", { label: "Orders", to: "/orders" }, s);
    rememberRecent("k", { label: "Stores", to: "/stores" }, s);
    expect(readRecent("k", s).map((p) => p.to)).toEqual(["/stores", "/orders"]);
  });

  it("keeps only the last few", () => {
    const s = memory();
    for (let i = 0; i < MAX_RECENT + 3; i++) rememberRecent("k", { label: `P${i}`, to: `/p${i}` }, s);
    expect(readRecent("k", s)).toHaveLength(MAX_RECENT);
    expect(readRecent("k", s)[0].to).toBe(`/p${MAX_RECENT + 2}`);
  });

  it("is per key, so one person's pages are never shown to another", () => {
    const s = memory();
    rememberRecent("crm.palette.recent.alice", { label: "Cash", to: "/cash" }, s);
    expect(readRecent("crm.palette.recent.bob", s)).toEqual([]);
  });

  it("treats a corrupt or foreign value as empty and drops entries that are not in-app paths", () => {
    const s = memory();
    s.setItem("bad", "{not json");
    expect(readRecent("bad", s)).toEqual([]);
    s.setItem("odd", JSON.stringify([{ label: "x", to: "https://elsewhere.example" }, { label: "ok", to: "/ok" }, 7, null]));
    expect(readRecent("odd", s)).toEqual([{ label: "ok", to: "/ok" }]);
  });

  it("does nothing, and does not throw, when storage is unavailable or refuses writes", () => {
    expect(readRecent("k", null)).toEqual([]);
    expect(() => rememberRecent("k", { label: "A", to: "/a" }, null)).not.toThrow();
    const full = { getItem: () => null, setItem: () => { throw new Error("quota"); } };
    expect(() => rememberRecent("k", { label: "A", to: "/a" }, full)).not.toThrow();
  });
});
