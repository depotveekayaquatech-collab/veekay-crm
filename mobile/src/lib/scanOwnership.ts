/**
 * Whose queued scan is it? Pure rules (no storage, no network) so they can be tested on their own.
 *
 * Every queued scan carries the id of the account that scanned it. A scan is shown to, and sent for, that account only. A scan with no owner
 * (queued by an older version of the app) is kept but "unassigned": it is never shown and never sent, because sending it under whoever is signed
 * in would save it under the wrong name.
 */
export const UNASSIGNED = "unassigned";

export interface Owned {
  owner_id?: string;
}

/** Older queues have no owner on their items: mark them unassigned (nothing is deleted). */
export function adoptLegacy<T extends Owned>(items: T[]): T[] {
  return items.map((i) => (i.owner_id ? i : { ...i, owner_id: UNASSIGNED }));
}

/** What the signed-in account may see. Nobody signed in sees nothing. */
export function visibleTo<T extends Owned>(items: T[], owner: string | null): T[] {
  return owner ? items.filter((i) => i.owner_id === owner) : [];
}

/** What may be sent right now: only the signed-in account's own scans. */
export function sendableBy<T extends Owned>(items: T[], owner: string | null): T[] {
  return visibleTo(items, owner);
}

/** True while the account that started a send is still the one signed in (checked before EVERY request of a flush). */
export function stillSameAccount(started: string, current: string | null): boolean {
  return current === started;
}
