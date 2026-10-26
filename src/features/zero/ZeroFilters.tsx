import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { MultiSelect } from "@/features/zero/MultiSelect";
import { PRESETS, type Preset, useZeroFilters } from "@/features/zero/useZeroFilters";
import type { Options } from "@/features/zero/api";

type Filters = ReturnType<typeof useZeroFilters>;

interface Props {
  f: Filters;
  options: Options | undefined;
  /** which controls this sub-tab uses: dates are picked in the Weekly / Monthly tabs themselves; the streak controls only apply to Zero Streaks */
  show: { dates?: boolean; streak?: boolean; status?: boolean };
  /** extra buttons at the end of the bar (export ...) */
  actions?: React.ReactNode;
}

const STATUS = [{ value: "", label: "All" }, { value: "pending", label: "Pending" }, { value: "reviewed", label: "Reviewed" }, { value: "verified", label: "Verified" }, { value: "flagged", label: "Flagged" }];
const N_CHOICES = [2, 3, 4, 5, 6, 7, 10, 15, 30];
const UNMARKED = [{ value: "break", label: "Break streak (default)" }, { value: "ignore", label: "Ignore (skip them)" }, { value: "count", label: "Count as zero" }];

/** The filters every Zero Review sub-tab shares. All of them are applied by the server and kept in the URL. */
export function ZeroFilters({ f, options, show, actions }: Props) {
  const v = f.values;
  const [custom, setCustom] = useState(false);
  const nChoice = v.n === 0 ? "0" : N_CHOICES.includes(v.n) && !custom ? String(v.n) : "custom";

  return (
    <form className="grid gap-3 rounded-2xl border border-surface-border bg-surface p-4 sm:grid-cols-2 lg:grid-cols-4" onSubmit={(e) => e.preventDefault()} aria-label="Filters">
      <MultiSelect label="Region" allLabel="All regions" value={v.regions} onChange={(x) => f.patch({ region: x.join(",") })} options={(options?.regions ?? []).map((r) => ({ value: r.id, label: r.name }))} />
      <MultiSelect label="Employee" allLabel="All employees" value={v.employees} onChange={(x) => f.patch({ employee: x.join(",") })} options={(options?.employees ?? []).map((e) => ({ value: e.id, label: e.name, hint: e.code }))} />
      {(options?.platforms.length ?? 0) > 1 && (
        <Select label="Platform" value={v.platform} onChange={(e) => f.patch({ platform: e.target.value })} placeholder="All platforms" options={(options?.platforms ?? []).map((p) => ({ value: p.slug, label: p.name }))} />
      )}
      <Input label="Store" value={v.q} onChange={(e) => f.patch({ q: e.target.value })} placeholder="Name, outlet ID or code" />
      {show.status !== false && <Select label="Review status" value={v.status} onChange={(e) => f.patch({ status: e.target.value })} options={STATUS} />}

      {show.dates && (
        <>
          <Select label="Period" value={f.preset} onChange={(e) => f.setPreset(e.target.value as Preset)} options={PRESETS} />
          <Input label="From" type="date" value={v.from} max={v.to} onChange={(e) => f.patch({ preset: "custom", from: e.target.value, to: v.to })} />
          <Input label="To" type="date" value={v.to} min={v.from} onChange={(e) => f.patch({ preset: "custom", from: v.from, to: e.target.value })} />
        </>
      )}

      {show.streak && (
        <>
          <Select label="Consecutive zeros" value={nChoice} onChange={(e) => { const x = e.target.value; if (x === "custom") { setCustom(true); if (!v.n) f.patch({ n: "2" }); } else { setCustom(false); f.patch({ n: x === "0" ? undefined : x }); } }}
            options={[{ value: "0", label: "Off" }, ...N_CHOICES.map((n) => ({ value: String(n), label: `${n} or more days` })), { value: "custom", label: "Custom…" }]} />
          {nChoice === "custom" && <Input label="Custom number of days" type="number" min={1} max={366} value={String(v.n || "")} onChange={(e) => f.patch({ n: e.target.value })} />}
          <Select label="Unmarked days" value={v.unmarked} onChange={(e) => f.patch({ unmarked: e.target.value === "break" ? undefined : e.target.value })} options={UNMARKED} />
          <Input label="Stores with unmarked days ≥" type="number" min={0} max={366} value={v.unmarkedGe ? String(v.unmarkedGe) : ""} onChange={(e) => f.patch({ ugt: e.target.value })} placeholder="e.g. 3" />
          <Select label="Sort by" value={v.sort} onChange={(e) => f.patch({ sort: e.target.value === "streak" ? undefined : e.target.value })}
            options={[{ value: "streak", label: "Longest streak" }, { value: "unmarked", label: "Most unmarked days" }, { value: "zero_days", label: "Most zero days" }, { value: "store", label: "Store name" }]} />
        </>
      )}

      <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-4">
        <Button type="button" variant="ghost" onClick={() => { setCustom(false); f.clear(); }}>Clear filters</Button>
        {actions}
      </div>
    </form>
  );
}
