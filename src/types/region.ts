export interface Region {
  id: string;
  name: string;
  code: string;
  isActive: boolean;
  storeCount: number;
}

export interface RegionWire {
  id: string;
  name: string;
  code: string;
  is_active: boolean;
  store_count: number;
}

export function toRegion(w: RegionWire): Region {
  return {
    id: w.id,
    name: w.name,
    code: w.code,
    isActive: w.is_active,
    storeCount: w.store_count,
  };
}

export interface RegionInput {
  name: string;
  code: string;
}
