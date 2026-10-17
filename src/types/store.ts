export type StoreStatus = "LIVE" | "PENDING" | "CLOSE";

export interface Store {
  id: string;
  name: string;
  externalCode: string;
  status: StoreStatus;
  entity: string | null;
  startDate: string | null;
  state: string | null;
  city: string | null;
  address: string | null;
  pocName: string | null;
  pocNumber: string | null;
  vendorName: string | null;
  vendorNumber: string | null;
  regionId: string | null;
  regionName: string | null;
  partnerOrganizationId: string;
  partnerSlug: string | null;
  partnerName: string | null;
}

export interface StoreWire {
  id: string;
  name: string;
  external_code: string;
  status: StoreStatus;
  entity?: string | null;
  start_date?: string | null;
  state: string | null;
  city: string | null;
  address: string | null;
  poc_name: string | null;
  poc_number: string | null;
  vendor_name: string | null;
  vendor_number: string | null;
  region_id: string | null;
  region_name: string | null;
  partner_organization_id: string;
  partner_slug: string | null;
  partner_name: string | null;
}

export function toStore(w: StoreWire): Store {
  return {
    id: w.id,
    name: w.name,
    externalCode: w.external_code,
    status: w.status,
    entity: w.entity ?? null,
    startDate: w.start_date ?? null,
    state: w.state,
    city: w.city,
    address: w.address,
    pocName: w.poc_name,
    pocNumber: w.poc_number,
    vendorName: w.vendor_name,
    vendorNumber: w.vendor_number,
    regionId: w.region_id,
    regionName: w.region_name,
    partnerOrganizationId: w.partner_organization_id,
    partnerSlug: w.partner_slug,
    partnerName: w.partner_name,
  };
}

export interface StoreSyncResult {
  platform: string;
  created: number;
  updated: number;
  unchanged: number;
  rowsRead: number;
  vendorChanges: number;
  /** New stores that were added although the sheet gave no readable start date. */
  withoutStartDate: number;
  warnings: string[];
}

export function toSyncResult(w: {
  platform: string;
  created: number;
  updated: number;
  unchanged: number;
  rows_read: number;
  vendor_changes?: number;
  without_start_date?: number;
  warnings: string[];
}): StoreSyncResult {
  return {
    platform: w.platform,
    created: w.created,
    updated: w.updated,
    unchanged: w.unchanged,
    rowsRead: w.rows_read,
    vendorChanges: w.vendor_changes ?? 0,
    withoutStartDate: w.without_start_date ?? 0,
    warnings: w.warnings,
  };
}

export interface VendorPeriod {
  vendorName: string;
  vendorNumber: string | null;
  startDate: string | null;
  endDate: string | null; // null = the current vendor
  startConfirmed: boolean;
  current: boolean;
  /** Who made the change; null for vendors recorded before this was tracked. */
  changedBy: string | null;
  source: string;
  recordedOn: string | null;
}

export function toVendorPeriod(w: {
  vendor_name: string;
  vendor_number: string | null;
  start_date: string | null;
  end_date: string | null;
  start_confirmed: boolean;
  current: boolean;
  changed_by?: string | null;
  source?: string;
  recorded_on?: string | null;
}): VendorPeriod {
  return {
    vendorName: w.vendor_name,
    vendorNumber: w.vendor_number,
    startDate: w.start_date,
    endDate: w.end_date,
    startConfirmed: w.start_confirmed,
    current: w.current,
    changedBy: w.changed_by ?? null,
    source: w.source ?? "",
    recordedOn: w.recorded_on ?? null,
  };
}

export interface StoreInput {
  name: string;
  external_code: string;
  partner_organization_id: string;
  region_id?: string | null;
  state?: string | null;
  city?: string | null;
  address?: string | null;
  poc_name?: string | null;
  poc_number?: string | null;
  vendor_name?: string | null;
  vendor_number?: string | null;
  start_date?: string | null;
  status?: StoreStatus;
}
