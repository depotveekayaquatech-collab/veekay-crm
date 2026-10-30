/** The few pages a person opened last through the command palette, kept in their own browser only. Pages only: no store, employee or record names are stored. */
export interface RecentPage {
  label: string;
  to: string;
}

export const MAX_RECENT = 5;

type Store = Pick<Storage, "getItem" | "setItem">;

const browserStorage = (): Store | null => {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;                                    // storage can be blocked (private window, site data off)
  }
};

export function readRecent(key: string, store: Store | null = browserStorage()): RecentPage[] {
  if (!store) return [];
  try {
    const raw: unknown = JSON.parse(store.getItem(key) ?? "[]");
    if (!Array.isArray(raw)) return [];
    return raw.filter((x): x is RecentPage => typeof x?.label === "string" && typeof x?.to === "string" && x.to.startsWith("/")).slice(0, MAX_RECENT);
  } catch {
    return [];                                      // a corrupt value is the same as none
  }
}

export function rememberRecent(key: string, page: RecentPage, store: Store | null = browserStorage()): void {
  if (!store) return;
  try {
    const next = [page, ...readRecent(key, store).filter((x) => x.to !== page.to)].slice(0, MAX_RECENT);
    store.setItem(key, JSON.stringify(next));
  } catch {
    /* the palette works without it */
  }
}
