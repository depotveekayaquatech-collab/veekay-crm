/** Shared by the sheet panels: the "pick the right store for these outlets" step. */
export const SKIP = "skip";

export interface Suggestion {
  store_id: string;
  name: string;
  code: string;
}

/** An outlet in the sheet that matched no single store. */
export interface PickerRow {
  row: number;
  name: string;
  total: number;
  reason: string;
  suggestions: Suggestion[];
}
