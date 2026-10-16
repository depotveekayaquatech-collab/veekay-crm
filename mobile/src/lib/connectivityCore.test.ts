import test from "node:test";
import assert from "node:assert/strict";
import { createConnectivity, shouldRetryQuery, probeDelayMs, type Clock } from "./connectivityCore.ts";

function fake() {
  let t = 0;
  const timers: { at: number; fn: () => void; id: number }[] = [];
  let n = 0;
  const clock: Clock = {
    now: () => t,
    setTimeout: (fn, ms) => { const id = ++n; timers.push({ at: t + ms, fn, id }); return id; },
    clearTimeout: (h) => { const i = timers.findIndex((x) => x.id === h); if (i >= 0) timers.splice(i, 1); },
  };
  const advance = (ms: number) => { t += ms; for (const x of [...timers]) if (x.at <= t) { timers.splice(timers.indexOf(x), 1); x.fn(); } };
  return { clock, advance };
}

test("offline banner waits out brief drops (wifi to data switch)", () => {
  const f = fake(); const c = createConnectivity(f.clock);
  c.setDeviceConnected(false); f.advance(1000); c.setDeviceConnected(true); f.advance(5000);
  assert.equal(c.getStatus(), "ok");
});
test("sustained offline shows once, reconnect clears", () => {
  const f = fake(); const c = createConnectivity(f.clock); let changes = 0; c.subscribe(() => changes++);
  c.setDeviceConnected(false); c.setDeviceConnected(false); f.advance(3000);
  assert.equal(c.getStatus(), "offline"); c.setDeviceConnected(true);
  assert.equal(c.getStatus(), "ok"); assert.equal(changes, 2);
});
test("one failed request is not an outage; two are", () => {
  const f = fake(); const c = createConnectivity(f.clock);
  c.reportFailure("unreachable"); assert.equal(c.getStatus(), "ok");
  c.reportFailure("timeout"); assert.equal(c.getStatus(), "unreachable");
  c.reportSuccess(); assert.equal(c.getStatus(), "ok");
});
test("old failures expire", () => {
  const f = fake(); const c = createConnectivity(f.clock);
  c.reportFailure("unreachable"); f.advance(61_000); c.reportFailure("unreachable");
  assert.equal(c.getStatus(), "ok");
});
test("failures while device is offline never claim the server is down", () => {
  const f = fake(); const c = createConnectivity(f.clock);
  c.setDeviceConnected(false); c.reportFailure("unreachable"); c.reportFailure("unreachable");
  assert.notEqual(c.getStatus(), "unreachable");
});
test("retry policy: bounded, reads only, never 4xx/429", () => {
  assert.equal(shouldRetryQuery(0, { status: 0 }), true);
  assert.equal(shouldRetryQuery(2, { status: 0 }), false);
  assert.equal(shouldRetryQuery(0, { status: 429 }), false);
  assert.equal(shouldRetryQuery(0, { status: 401 }), false);
  assert.equal(shouldRetryQuery(0, { status: 503 }), true);
  assert.equal(probeDelayMs(0), 10_000); assert.equal(probeDelayMs(9), 60_000);
});
