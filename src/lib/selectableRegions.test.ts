import { describe, expect, it } from "vitest";
import { selectableRegions } from "./selectableRegions";
import type { Region } from "@/types/region";

const r = (id: string, o: Partial<Region> = {}): Region => ({ id, name: id, code: id.toUpperCase(), isActive: true, storeCount: 10, ...o });

describe("selectableRegions", () => {
  it("leaves out a deactivated region with no stores (the empty DELBLR the import created)", () => {
    const list = [r("north"), r("delblr", { isActive: false, storeCount: 0 })];
    expect(selectableRegions(list).map((x) => x.id)).toEqual(["north"]);
  });

  it("keeps active regions even when they are empty (a new region is selectable before it has stores)", () => {
    expect(selectableRegions([r("new", { storeCount: 0 })]).map((x) => x.id)).toEqual(["new"]);
  });

  it("keeps a deactivated region that still owns stores", () => {
    expect(selectableRegions([r("old", { isActive: false, storeCount: 12 })]).map((x) => x.id)).toEqual(["old"]);
  });

  it("never drops the region a record being edited already uses", () => {
    const list = [r("delblr", { isActive: false, storeCount: 0 })];
    expect(selectableRegions(list, ["delblr"]).map((x) => x.id)).toEqual(["delblr"]);
    expect(selectableRegions(list, [null, undefined]).map((x) => x.id)).toEqual([]);
  });

  it("does not change the order or the objects", () => {
    const list = [r("b"), r("a")];
    expect(selectableRegions(list)).toEqual(list);
  });
});
