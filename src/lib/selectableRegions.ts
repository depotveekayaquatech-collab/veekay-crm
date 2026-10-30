import type { Region } from "@/types/region";

/**
 * Which regions a dropdown should offer. A region that was deactivated AND has no stores is left out: nothing can belong to it, so it is only a choice that does
 * not exist (an empty region the store import made from a sheet name). A deactivated region that still has stores stays, and so does any region in `keep` (the
 * one the record being edited already uses), so editing never loses a saved value.
 */
export function selectableRegions(regions: Region[], keep: readonly (string | null | undefined)[] = []): Region[] {
  return regions.filter((r) => r.isActive || r.storeCount > 0 || keep.includes(r.id));
}
