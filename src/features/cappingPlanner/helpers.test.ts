import { describe, expect, it } from "vitest";
import { buildRequest, parseCount, priorityLines, removePriorityLine, type PlannerForm } from "./helpers";

const form: PlannerForm = { month: "2026-11", project: "zepto", mode: "priority_first", storeLimitText: "", targetText: "", priorityText: "" };

describe("planner inputs", () => {
  it("reads whole numbers, allows separators and refuses anything else", () => {
    expect(parseCount("")).toEqual({ value: null, error: null });
    expect(parseCount("50,000")).toEqual({ value: 50000, error: null });
    expect(parseCount(" 200 ").value).toBe(200);
    expect(parseCount("12.5").error).toBeTruthy();
    expect(parseCount("-3").error).toBeTruthy();
    expect(parseCount("abc").error).toBeTruthy();
  });

  it("keeps the pasted order, ignores blank lines and removes one line by its position", () => {
    const text = "  DEL-ROHINI Sector 15 \r\n\nDEL-SHAKTI NAGAR\nGZB-GAUR CITY\n";
    expect(priorityLines(text)).toEqual(["DEL-ROHINI Sector 15", "DEL-SHAKTI NAGAR", "GZB-GAUR CITY"]);
    expect(removePriorityLine(text, 2)).toBe("DEL-ROHINI Sector 15\nGZB-GAUR CITY");
    expect(removePriorityLine(text, 9)).toBe("DEL-ROHINI Sector 15\nDEL-SHAKTI NAGAR\nGZB-GAUR CITY");
  });

  it("builds the request, with a blank limit meaning every eligible store and a blank target meaning 0", () => {
    const r = buildRequest({ ...form, storeLimitText: "200", targetText: "50,000", priorityText: "A\nB" });
    expect(r.request).toEqual({ month: "2026-11", project: "zepto", mode: "priority_first", storeLimit: 200, target: 50000, priority: ["A", "B"] });
    expect(buildRequest(form).request).toMatchObject({ storeLimit: null, target: 0, priority: [] });
  });

  it("refuses a zero or fractional store limit and a bad target, and says which field", () => {
    expect(buildRequest({ ...form, storeLimitText: "0" }).errors.storeLimit).toBeTruthy();
    expect(buildRequest({ ...form, storeLimitText: "1.5" }).request).toBeNull();
    expect(buildRequest({ ...form, targetText: "x" }).errors.target).toBeTruthy();
  });
});
