export interface Option {
  value: string;
  label: string;
}

/** Distinct, sorted options built from whatever list is on screen — so a dropdown only offers what exists for the current platform. */
export function distinctOptions<T>(items: T[], pick: (item: T) => Option | null): Option[] {
  const map = new Map<string, Option>();
  for (const item of items) {
    const o = pick(item);
    if (o && o.value && !map.has(o.value)) map.set(o.value, o);
  }
  return [...map.values()].sort((a, b) => a.label.localeCompare(b.label));
}
