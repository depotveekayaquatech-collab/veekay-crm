import { Select } from "@/components/ui/Select";
import { SKIP, type PickerRow } from "./sheetPicker";

interface Props {
  rows: PickerRow[];
  /** unmatched sheet row -> chosen store id, or SKIP */
  choice: Record<number, string>;
  /** every store the person may pick, already labelled */
  allOptions: { value: string; label: string }[];
  onChoose: (row: number, value: string) => void;
}

/** Outlets in an uploaded sheet that matched no single store: pick the right store for each (the likely ones first), or skip it. */
export function UnmatchedPicker({ rows, choice, allOptions, onChoose }: Props) {
  const unresolved = rows.filter((u) => !choice[u.row]).length;
  return (
    <div className="rounded-xl border border-status-warning bg-status-warning-soft px-4 py-3">
      <p className="text-sm font-semibold text-gray-800">Pick the right store for these (or skip them)</p>
      <div className="mt-3 flex flex-col gap-3">
        {rows.map((u) => (
          <div key={u.row} className="grid items-end gap-3 md:grid-cols-[1fr_2fr]">
            <div className="text-sm">
              <p className="font-semibold text-gray-900">{u.name}</p>
              <p className="text-xs text-gray-600">Total {u.total.toLocaleString("en-IN")} · {u.reason}</p>
            </div>
            <Select
              label="Store"
              searchable
              placeholder="Choose a store…"
              value={choice[u.row] ?? ""}
              options={[
                ...u.suggestions.map((s) => ({ value: s.store_id, label: `★ ${s.code} — ${s.name}` })),
                { value: SKIP, label: "Skip this outlet" },
                ...allOptions.filter((o) => !u.suggestions.some((s) => s.store_id === o.value)),
              ]}
              onChange={(e) => onChoose(u.row, e.target.value)}
            />
          </div>
        ))}
      </div>
      {unresolved > 0 && <p className="mt-3 text-xs text-gray-600">{unresolved} not chosen yet; they will be left out until you pick a store or skip them.</p>}
    </div>
  );
}
