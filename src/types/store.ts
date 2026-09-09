export type StoreStatus = "LIVE" | "PENDING" | "CLOSE";

export interface Store {
  id: string;
  name: string;
  externalCode: string;
  status: StoreStatus;
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
  warnings: string[];
}

export function toSyncResult(w: {
  platform: string;
  created: number;
  updated: number;
  unchanged: number;
  rows_read: number;
  warnings: string[];
}): StoreSyncResult {
  return {
    platform: w.platform,
    created: w.created,
    updated: w.updated,
    unchanged: w.unchanged,
    rowsRead: w.rows_read,
    warnings: w.warnings,
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
  status?: StoreStatus;
}
