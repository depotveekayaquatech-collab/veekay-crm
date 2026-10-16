import { camelize } from "@/lib/camel";
import { apiRequest } from "@/services/api";

export interface RateLine {
  scope: "city" | "store";
  city: string | null;
  storeName: string | null;
  outletId: string | null;
  oldRate: string | null;
  newRate: string;
  storesAffected?: number;
}

export interface RateUploadResult {
  applied: boolean;
  needsConfirmation: boolean;
  effectiveFrom: string;
  new: number;
  changed: number;
  unchanged: number;
  storesAffected: number;
  changes: RateLine[];
  newRates: RateLine[];
  warnings: string[];
}

export interface CurrentRate {
  scope: "city" | "store";
  city: string | null;
  storeName: string | null;
  outletId: string | null;
  rate: string;
  effectiveFrom: string;
}

export async function listVendorRates(platform: string): Promise<CurrentRate[]> {
  return camelize<CurrentRate[]>(await apiRequest(`/vendor-rates?platform=${encodeURIComponent(platform)}`));
}

/** Without `confirm`, a sheet that would change existing rates writes nothing and returns the list of changes. */
export async function uploadVendorRates(file: File, platform: string, confirm: boolean, effectiveFrom?: string): Promise<RateUploadResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("platform", platform);
  form.append("confirm", String(confirm));
  if (effectiveFrom) form.append("effective_from", effectiveFrom);
  return camelize<RateUploadResult>(await apiRequest("/vendor-rates/upload", { method: "POST", body: form }));
}
