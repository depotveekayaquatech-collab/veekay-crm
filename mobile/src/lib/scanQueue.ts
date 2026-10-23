/**
 * Offline-safe bottle scanning.
 *
 * Every scan gets a unique scan_id the moment the camera reads it. The API treats a repeated scan_id as "already
 * recorded", so re-sending after a dropped connection, an app restart or a double tap can never count a bottle twice.
 * A scan that can't be sent right now stays in this queue (kept on the phone) and is sent when the network is back.
 *
 * Whose scan is it? Every queued scan carries the id of the account that scanned it, and is only ever sent while THAT account is signed in.
 * Two people sharing a phone therefore never see or send each other's scans, and a scan can never be saved under the wrong name.
 * (Before this, the queue was one list for the whole phone: a scan left unsent by one person was sent with the next person's login.)
 */
import AsyncStorage from "@react-native-async-storage/async-storage";
import NetInfo from "@react-native-community/netinfo";
import { randomUUID } from "expo-crypto";
import { ApiError } from "@/api/client";
import { staffApi, type Direction, type ScanResult } from "@/api/staff";
import { adoptLegacy, sendableBy, stillSameAccount, visibleTo } from "@/lib/scanOwnership";

const KEY = "veekay.scanQueue.v1";

export interface QueuedScan {
  /** The account that scanned it. A scan from an older app version has none: it is kept but never sent or shown (its owner is unknown). */
  owner_id?: string;
  scan_id: string;
  serial: string;
  direction: Direction;
  store_id: string | null;
  scanned_at: string;
}

export interface Rejected extends QueuedScan {
  reason: string;
}

interface State {
  pending: QueuedScan[];
  rejected: Rejected[];   // the server refused these (unknown code, wrong store ...): shown to the person, never retried
}

let state: State = { pending: [], rejected: [] };
let owner: string | null = null;                  // the signed-in employee; null = nobody, so nothing is sent
let view: State = { pending: [], rejected: [] }; // what the signed-in employee may see (stable between changes)
let loaded = false;
let flushing: Promise<void> | null = null;
const listeners = new Set<() => void>();

function emit() {
  view = { pending: visibleTo(state.pending, owner), rejected: visibleTo(state.rejected, owner) };
  listeners.forEach((l) => l());
}

/** Tell the queue who is signed in. Called BEFORE the next person's login is used and as soon as a session ends, so a flush can never run under the wrong account. */
export function setQueueOwner(id: string | null): void {
  owner = id;
  emit();
}

async function persist() {
  await AsyncStorage.setItem(KEY, JSON.stringify(state)).catch(() => undefined);
}

export async function loadQueue(): Promise<void> {
  if (loaded) return;
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (raw) {
      state = { pending: [], rejected: [], ...(JSON.parse(raw) as Partial<State>) };
      // Scans queued by an older version of the app have no owner. They are kept (nothing is deleted) but marked unassigned, so they are
      // never sent under whoever happens to sign in next.
      state = { pending: adoptLegacy(state.pending), rejected: adoptLegacy(state.rejected) };
    }
  } catch {
    state = { pending: [], rejected: [] };
  }
  loaded = true;
  emit();
}

export function subscribeQueue(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export const getQueue = (): State => view;

export async function clearRejected(): Promise<void> {
  state = { ...state, rejected: state.rejected.filter((r) => r.owner_id !== owner) };
  emit();
  await persist();
}

export type Outcome =
  | { kind: "done"; scanId: string; result: ScanResult }
  | { kind: "queued"; scanId: string }
  | { kind: "rejected"; scanId: string; reason: string };

/** No connection, a timeout, a server error, or an expired session (the scan stays queued until they sign in again)
 * are worth retrying; anything else is the server's decision about this scan. */
function retryable(e: unknown): boolean {
  return e instanceof ApiError ? e.status === 0 || e.status === 401 || e.status >= 500 : true;
}

/** Records one scan: sent now when online, otherwise kept for later. Never loses a scan. */
export async function submitScan(serial: string, direction: Direction, storeId: string | null): Promise<Outcome> {
  await loadQueue();
  if (!owner) return { kind: "rejected", scanId: "", reason: "Sign in again before scanning." };
  const item: QueuedScan = { owner_id: owner, scan_id: randomUUID(), serial: serial.trim(), direction, store_id: storeId, scanned_at: new Date().toISOString() };
  // Written first: if the app dies mid-request the scan is still on the phone and its scan_id makes the resend safe.
  state = { ...state, pending: [...state.pending, item] };
  emit();
  await persist();
  try {
    const result = await staffApi.scan(toBody(item));
    await drop(item.scan_id);
    return { kind: "done", scanId: item.scan_id, result };
  } catch (e) {
    if (retryable(e)) return { kind: "queued", scanId: item.scan_id };
    const reason = e instanceof Error ? e.message : "Refused by the server.";
    await reject(item, reason);
    return { kind: "rejected", scanId: item.scan_id, reason };
  }
}

const toBody = (i: QueuedScan) => ({ serial: i.serial, direction: i.direction, store_id: i.store_id, scanned_at: i.scanned_at, scan_id: i.scan_id });

async function drop(scanId: string) {
  state = { ...state, pending: state.pending.filter((p) => p.scan_id !== scanId) };
  emit();
  await persist();
}

async function reject(item: QueuedScan, reason: string) {
  state = { pending: state.pending.filter((p) => p.scan_id !== item.scan_id), rejected: [{ ...item, reason }, ...state.rejected].slice(0, 100) };
  emit();
  await persist();
}

/** Sends everything waiting, oldest first, stopping at the first connection problem. Safe to call any time. */
export function flushQueue(): Promise<{ sent: number; left: number }> {
  if (!flushing) {
    flushing = (async () => {
      await loadQueue();
      let sent = 0;
      const mine = owner;
      if (!mine) return;
      for (const item of sendableBy(state.pending, mine)) {
        if (!stillSameAccount(mine, owner)) break;                  // somebody else signed in meanwhile: stop, never send under another account
        try {
          await staffApi.scan(toBody(item));
          await drop(item.scan_id);
          sent++;
        } catch (e) {
          if (retryable(e)) break;
          await reject(item, e instanceof Error ? e.message : "Refused by the server.");
        }
      }
      lastFlush = { sent, left: sendableBy(state.pending, mine).length };
    })().finally(() => {
      flushing = null;
    });
  }
  return flushing.then(() => lastFlush);
}

let lastFlush = { sent: 0, left: 0 };

/** Starts sending whenever the phone regains a connection. Returns the unsubscribe function. */
export function startAutoFlush(): () => void {
  void loadQueue().then(() => flushQueue());
  const off = NetInfo.addEventListener((s) => {
    if (s.isConnected && s.isInternetReachable !== false) void flushQueue();
  });
  return off;
}
