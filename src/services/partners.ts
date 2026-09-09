import { apiRequest } from "@/services/api";
import type { Partner } from "@/types/partner";

export function listPartners(): Promise<Partner[]> {
  return apiRequest<Partner[]>("/partners");
}
