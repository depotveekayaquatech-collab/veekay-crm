import type { PermissionGroup } from "@/types/employee";

interface Props {
  groups: PermissionGroup[];
  value: Set<string>;
  onChange: (next: Set<string>) => void;
}

/** One bordered card per permission group, each with its own Select all / Clear. Used for both admin and employee access. */
export function PermissionGrid({ groups, value, onChange }: Props) {
  function toggle(code: string) {
    const next = new Set(value);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    onChange(next);
  }

  function toggleGroup(codes: string[], on: boolean) {
    const next = new Set(value);
    codes.forEach((c) => (on ? next.add(c) : next.delete(c)));
    onChange(next);
  }

  return (
    <div className="grid gap-3 md:grid-cols-2">
      {groups.map((g) => {
        const codes = g.permissions.map((p) => p.code);
        const all = codes.every((c) => value.has(c));
        return (
          <div key={g.key} className="rounded-lg border border-surface-border p-3">
            <div className="mb-1.5 flex items-center justify-between">
              <p className="text-xs font-bold text-gray-500">{g.label}</p>
              <button type="button" className="text-[11px] font-semibold text-brand-600 hover:text-brand-700" onClick={() => toggleGroup(codes, !all)}>
                {all ? "Clear" : "Select all"}
              </button>
            </div>
            <div className="flex flex-col gap-1.5">
              {g.permissions.map((p) => (
                <label key={p.code} className="flex items-start gap-2 text-sm text-gray-700">
                  <input type="checkbox" checked={value.has(p.code)} onChange={() => toggle(p.code)} className="mt-0.5 h-4 w-4 rounded border-surface-border text-brand-500 focus:ring-brand-500" />
                  {p.description}
                </label>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
