import { describe, expect, it } from "vitest";
import { basisLine, formatEmployee, signedCount, formatReport, pickEmployees, type ReportRow } from "./performanceReport";

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

  it("says what it counted, so two pasted reports can be compared later", () => {
    const basis = basisLine(29, "2026-10-30T05:07:00Z");
    expect(basis).toBe("Counted over 29 days, holidays included. Taken 30 Oct, 10:37 am IST");
    const lines = formatReport("Blinkit - Employee performance, October 2026", [row()], basis).split("\n");
    expect(lines.slice(0, 4)).toEqual(["Blinkit - Employee performance, October 2026", "Entries = marked / total needed for 100%", basis, ""]);
  });

  it("shows the change since the previous report with a sign: +80 for new entries, -12 for a drop, 0 for none", () => {
    expect(formatEmployee(row({ change: 80 }))).toBe("Employee name - Harshita\nEntries - 460 / 500\nEntries change - +80\nPercentage - 92%\nNo. of stores - 20");
    expect(formatEmployee(row({ change: -12 }))).toContain("Entries - 460 / 500\nEntries change - -12\nPercentage");
    expect(formatEmployee(row({ change: 0 }))).toContain("Entries change - 0\n");
    expect(formatEmployee(row({ change: 12345 }))).toContain("Entries change - +12,345");
    expect(signedCount(-1234)).toBe("-1,234");
  });

  it("leaves the line out when there is nothing to compare with, and for people with no stores", () => {
    expect(formatEmployee(row())).not.toContain("Entries change");
    expect(formatEmployee(row({ change: null }))).not.toContain("Entries change");
    expect(formatEmployee(row({ no_stores: true, entries_made: 5, change: 3 }))).not.toContain("Entries change");
  });

  it("explains what the change is measured from", () => {
    expect(basisLine(29, "2026-10-30T05:07:00Z", "2026-10-29T05:07:00Z")).toBe(
      "Counted over 29 days, holidays included. Taken 30 Oct, 10:37 am IST. Entries change = gained (+) or lost (-) since 29 Oct, 10:37 am IST");
  });

  it("counts a single day in the singular, and adds nothing when no basis is given", () => {
    expect(basisLine(1)).toBe("Counted over 1 day, holidays included");
    expect(formatReport("x", [row()])).not.toContain("Counted over");
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
