# Connectivity fix: physical-device test procedure

Status: **PENDING** (no phone was available when the fix was written). Automated coverage is the 6 `node:test` tests in
`mobile/src/lib/connectivityCore.test.ts` (state machine and retry policy) and the vitest tests for the web toast bus and
`apiRequest`. They do not exercise a real radio, NetInfo or the server.

Use an Android phone with the new build (native) and Chrome on the same phone for the web app. Leave the phone on the
Dashboard unless a step says otherwise. "Banner" = the single bar at the top of the native app. On web, the equivalent is
the toast stack in the bottom corner.

| # | Step | Expected |
|---|---|---|
| 1 | Open the app with Wi-Fi/data on | No banner, no toast. Data loads. |
| 2 | Turn on airplane mode, wait 5 s | Native: ONE banner "You're offline…" after about 2.5 s. Lists show "Couldn't load this right now." Web: at most one toast "You appear to be offline…". Never a stack. |
| 3 | Open 3 different screens while offline | Still one banner / no new toasts (web: at most one per 20 s). |
| 4 | Turn airplane mode off | Banner disappears by itself within a few seconds. Open screens refresh once. |
| 5 | Open the app while already offline, then go online | Same as 2 then 4. |
| 6 | Wi-Fi off while mobile data is on (and the reverse) | No banner, or a banner for less than 3 s (the 2.5 s debounce hides a normal switch). |
| 7 | Backend unreachable but phone online: in the native build use a build pointed at a wrong host, or block `veekay-crm-api.fly.dev` with a DNS filter / firewall app | After 2 failed requests: ONE banner "Unable to reach Veekay CRM servers. Retrying…" (not "offline"). Web shows "Unable to reach the Veekay server…". |
| 8 | While 7 is active, watch network traffic (e.g. a proxy app) for 3 minutes | At most one `GET /health` at about 10 s, 20 s, 40 s, then every 60 s, and only with the app in the foreground. |
| 9 | Restore the backend | Within about a minute the banner clears and screens refresh. |
| 10 | Put the app in the background for 1 minute while offline, return | One banner at most; no burst of requests on return. |
| 11 | Offline: submit a ticket / cash purchase / leave request | The form keeps its text and shows the error. Nothing is sent when connectivity returns unless you press Submit again. Pressing Submit again after recovery creates ONE record (idempotency key). |
| 12 | Offline: scan a bottle (staff app) | The scan is queued ("waiting") and is sent automatically after reconnecting, once. |

Record per step: pass/fail, what was shown, and the phone model / Android version. Anything marked "pending" in release
notes stays pending until this table is filled in.
