import assert from "node:assert/strict";
import { test } from "node:test";
import { adoptLegacy, sendableBy, stillSameAccount, UNASSIGNED, visibleTo, type Owned } from "./scanOwnership.ts";

type Scan = Owned & { id: string };
const queue: Scan[] = [
  { id: "a1", owner_id: "emp-A" },
  { id: "a2", owner_id: "emp-A" },
  { id: "b1", owner_id: "emp-B" },
  { id: "old" },
];

test("each account sees and sends only its own scans", () => {
  const q = adoptLegacy(queue);
  assert.deepEqual(visibleTo(q, "emp-A").map((s) => s.id), ["a1", "a2"]);
  assert.deepEqual(visibleTo(q, "emp-B").map((s) => s.id), ["b1"]);
  assert.deepEqual(sendableBy(q, "emp-B").map((s) => s.id), ["b1"]);
});

test("nobody signed in: nothing is shown and nothing is sent", () => {
  const q = adoptLegacy(queue);
  assert.deepEqual(visibleTo(q, null), []);
  assert.deepEqual(sendableBy(q, null), []);
});

test("a scan from an older app version is kept but never given to whoever signs in next", () => {
  const q = adoptLegacy(queue);
  assert.equal(q.find((s) => s.id === "old")?.owner_id, UNASSIGNED);
  assert.equal(q.length, queue.length);                                     // nothing deleted
  for (const who of ["emp-A", "emp-B", "emp-C"]) assert.ok(!sendableBy(q, who).some((s) => s.id === "old"));
});

test("a stranger sees none of another person's scans", () => {
  assert.deepEqual(visibleTo(adoptLegacy(queue), "emp-C"), []);
});

test("a flush stops the moment a different account is signed in", () => {
  assert.equal(stillSameAccount("emp-A", "emp-A"), true);
  assert.equal(stillSameAccount("emp-A", "emp-B"), false);
  assert.equal(stillSameAccount("emp-A", null), false);                     // signed out mid-flush
});

test("adopting legacy items twice changes nothing", () => {
  const once = adoptLegacy(queue);
  assert.deepEqual(adoptLegacy(once), once);
});
