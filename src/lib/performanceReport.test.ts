import { describe, expect, it } from "vitest";
import { formatEmployee, formatReport, pickEmployees, type ReportRow } from "./performanceReport";

const row = (o: Partial<ReportRow> = {}): ReportRow => ({ employee_id: "e1", employee_name: "Harshita", stores: 20, expected: 500, done: 460, percent: 92, ...o });

describe("performance report text", () => {
  it("writes the four lines per employee: marked / total needed entries, percentage, stores", () => {
    expect(formatEmployee(row())).toBe("Employee name - Harshita\nEntries - 460 / 500\nPercentage - 92%\nNo. of stores - 20");
  });

  it("shows marked equal to the total at 100%", () => {
    expect(formatEmployee(row({ done: 480, expected: 480, percent: 100 }))).toContain("Entries - 480 / 480\nPercentage - 100%");
  });

  it("groups thousands the Indian way", () => {
    expect(formatEmployee(row({ done: 1234, expected: 123456 }))).toContain("Entries - 1,234 / 1,23,456");
  });

  it("puts a heading, then a blank line between employees", () => {
    const text = formatReport("Zepto - October 2026", [row(), row({ employee_id: "e2", employee_name: "Santosh", done: 480, expected: 480, percent: 100 })]);
    expect(text.split("\n")[0]).toBe("Zepto - October 2026");
    expect(text).toContain("Entries = marked / total needed for 100%");
    expect(text).toContain("No. of stores - 20\n\nEmployee name - Santosh");
  });

  it("is empty when nobody is selected", () => {
    expect(formatReport("x", [])).toBe("");
  });
});

describe("pickEmployees", () => {
  const rows = [row({ employee_id: "a", percent: 30 }), row({ employee_id: "b", percent: 50 }), row({ employee_id: "c", percent: 84 }), row({ employee_id: "d", percent: 85 })];
  it("filters by band, strictly under the line", () => {
    expect(pickEmployees(rows, "all")).toHaveLength(4);
    expect(pickEmployees(rows, "under50").map((r) => r.employee_id)).toEqual(["a"]);
    expect(pickEmployees(rows, "under85").map((r) => r.employee_id)).toEqual(["a", "b", "c"]);
  });
  it("picks one employee", () => {
    expect(pickEmployees(rows, "emp:c").map((r) => r.employee_id)).toEqual(["c"]);
    expect(pickEmployees(rows, "emp:zzz")).toEqual([]);
  });

  it("reports a person with no store of their own by the entries they made, and keeps them out of the percentage bands", () => {
    const helper = row({ employee_id: "e2", employee_name: "Vishwanjali", stores: 0, expected: 0, done: 0, percent: 0, entries_made: 312, no_stores: true });
    expect(formatEmployee(helper)).toBe("Employee name - Vishwanjali\nEntries made - 312\nNo. of stores - 0");
    const lead = row({ employee_id: "e3", employee_name: "Rahul", is_team_lead: true, corrected: 9 });
    expect(formatEmployee(lead)).toBe("Employee name - Rahul\nEntries - 460 / 500\nPercentage - 92%\nEntries corrected - 9\nNo. of stores - 20");
    expect(formatEmployee({ ...helper, is_team_lead: true, corrected: 4 })).toBe("Employee name - Vishwanjali\nEntries made - 312\nEntries corrected - 4\nNo. of stores - 0");
    expect(pickEmployees([row(), helper], "under50")).toEqual([]);
    expect(pickEmployees([row(), helper], "emp:e2")).toEqual([helper]);
  });
});
