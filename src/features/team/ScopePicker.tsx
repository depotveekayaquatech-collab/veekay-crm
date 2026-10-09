import { useQuery } from "@tanstack/react-query";
import { Select } from "@/components/ui/Select";
import { getLocations } from "@/services/employees";

interface Option {
  id: string;
  name: string;
}

type Tone = "brand" | "danger" | "success";
const TONES: Record<Tone, string> = {
  brand: "bg-brand-50 text-brand-700",
  danger: "bg-status-danger-soft text-status-danger",
  success: "bg-status-success-soft text-status-success",
};

function Chips({ items, onRemove, tone = "brand" }: { items: { key: string; label: string }[]; onRemove: (key: string) => void; tone?: Tone }) {
  if (!items.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((i) => (
        <span key={i.key} className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${TONES[tone]}`}>
          {i.label}
          <button type="button" aria-label={`Remove ${i.label}`} onClick={() => onRemove(i.key)} className="rounded-full px-1 leading-none hover:bg-black/10">
            ×
          </button>
        </span>
      ))}
    </div>
  );
}

interface Props {
  platformSlug: string;
  regionOptions: Option[];
  regionIds: string[];
  onRegionIds: (v: string[]) => void;
  excludedStates: string[];
  onExcludedStates: (v: string[]) => void;
  excludedCities: string[];
  onExcludedCities: (v: string[]) => void;
  includedStates: string[];
  onIncludedStates: (v: string[]) => void;
  includedCities: string[];
  onIncludedCities: (v: string[]) => void;
}

/**
 * What an employee covers: one or several regions, plus specific states / cities added on top (or on their own),
 * minus any states / cities to skip ("North and West, plus Goa, except Delhi and Pune").
 */
export function ScopePicker(p: Props) {
  const everywhere = useQuery({
    queryKey: ["scope-locations", p.platformSlug, "all"],
    enabled: Boolean(p.platformSlug),
    queryFn: () => getLocations(p.platformSlug, []),
    staleTime: 5 * 60_000,
  });
  const inRegions = useQuery({
    queryKey: ["scope-locations", p.platformSlug, p.regionIds],
    enabled: Boolean(p.platformSlug) && p.regionIds.length > 0,
    queryFn: () => getLocations(p.platformSlug, p.regionIds),
    staleTime: 5 * 60_000,
  });

  const nameOf = (id: string) => p.regionOptions.find((r) => r.id === id)?.name ?? "Region";
  const addable = p.regionOptions.filter((r) => !p.regionIds.includes(r.id));
  const lower = (list: string[]) => new Set(list.map((x) => x.toLowerCase()));
  const has = (list: string[], v: string) => lower(list).has(v.toLowerCase());
  const cityLabel = (c: { city: string; state: string }) => (c.state ? `${c.city}, ${c.state}` : c.city);

  const stateOptions = (all: string[] | undefined, taken: string[][]) =>
    (all ?? []).filter((s) => !taken.some((t) => has(t, s))).map((s) => ({ value: s, label: s }));
  const cityOptions = (all: { city: string; state: string }[] | undefined, taken: string[][]) =>
    (all ?? []).filter((c) => !taken.some((t) => has(t, c.city))).map((c) => ({ value: c.city, label: cityLabel(c) }));

  const removeFrom = (key: string, states: string[], setStates: (v: string[]) => void, cities: string[], setCities: (v: string[]) => void) =>
    key.startsWith("s:") ? setStates(states.filter((s) => `s:${s}` !== key)) : setCities(cities.filter((c) => `c:${c}` !== key));
  const asChips = (states: string[], cities: string[]) => [
    ...states.map((s) => ({ key: `s:${s}`, label: `State: ${s}` })),
    ...cities.map((c) => ({ key: `c:${c}`, label: `City: ${c}` })),
  ];

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-surface-border p-3.5">
      <div className="flex flex-col gap-2">
        <Chips items={p.regionIds.map((id) => ({ key: id, label: nameOf(id) }))} onRemove={(id) => p.onRegionIds(p.regionIds.filter((r) => r !== id))} />
        {addable.length > 0 && (
          <Select
            label={p.regionIds.length ? "Add another region" : "Regions"}
            value=""
            placeholder={p.regionIds.length ? "Add a region…" : "Choose one or more regions…"}
            onChange={(e) => e.target.value && p.onRegionIds([...p.regionIds, e.target.value])}
            options={addable.map((r) => ({ value: r.id, label: r.name }))}
          />
        )}
      </div>

      {p.platformSlug && (
        <div className="flex flex-col gap-3 border-t border-surface-border pt-3">
          <p className="text-[13px] font-semibold text-gray-700">Also give specific places (optional)</p>
          <Chips tone="success" items={asChips(p.includedStates, p.includedCities)} onRemove={(k) => removeFrom(k, p.includedStates, p.onIncludedStates, p.includedCities, p.onIncludedCities)} />
          <div className="grid gap-3 sm:grid-cols-2">
            <Select
              label="Add a state"
              value=""
              searchable
              placeholder="Choose a state…"
              onChange={(e) => e.target.value && p.onIncludedStates([...p.includedStates, e.target.value])}
              options={stateOptions(everywhere.data?.states, [p.includedStates, p.excludedStates])}
            />
            <Select
              label="Add a city"
              value=""
              searchable
              placeholder="Choose a city…"
              onChange={(e) => e.target.value && p.onIncludedCities([...p.includedCities, e.target.value])}
              options={cityOptions(everywhere.data?.cities, [p.includedCities, p.excludedCities])}
            />
          </div>
          <p className="text-xs text-gray-500">Added on top of the regions above, or on their own if no region is chosen.</p>
        </div>
      )}

      {p.regionIds.length > 0 && (
        <div className="flex flex-col gap-3 border-t border-surface-border pt-3">
          <p className="text-[13px] font-semibold text-gray-700">Skip these places (optional)</p>
          <Chips tone="danger" items={asChips(p.excludedStates, p.excludedCities)} onRemove={(k) => removeFrom(k, p.excludedStates, p.onExcludedStates, p.excludedCities, p.onExcludedCities)} />
          <div className="grid gap-3 sm:grid-cols-2">
            <Select
              label="Skip a state"
              value=""
              searchable
              placeholder="Choose a state…"
              onChange={(e) => e.target.value && p.onExcludedStates([...p.excludedStates, e.target.value])}
              options={stateOptions(inRegions.data?.states, [p.excludedStates, p.includedStates])}
            />
            <Select
              label="Skip a city"
              value=""
              searchable
              placeholder="Choose a city…"
              onChange={(e) => e.target.value && p.onExcludedCities([...p.excludedCities, e.target.value])}
              options={cityOptions(inRegions.data?.cities, [p.excludedCities, p.includedCities])}
            />
          </div>
          <p className="text-xs text-gray-500">Skipped places are taken out of everything above. Skipping always wins.</p>
        </div>
      )}
    </div>
  );
}
