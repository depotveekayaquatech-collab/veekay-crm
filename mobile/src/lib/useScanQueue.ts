import { useSyncExternalStore } from "react";
import { getQueue, subscribeQueue } from "@/lib/scanQueue";

/** Live view of the offline scan queue (what is waiting to be sent, and what the server refused). */
export function useScanQueue() {
  return useSyncExternalStore(subscribeQueue, getQueue, getQueue);
}
