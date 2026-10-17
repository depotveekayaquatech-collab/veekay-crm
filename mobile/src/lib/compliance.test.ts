import test from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULT_POLICY, describeSelection, fitWithin, fmtBytes, monthLabel, selectionSignature, shouldShrink, slotBadge, validateSelection,
} from "./compliance.ts";

const MB = 1024 * 1024;
const photo = (name = "a.jpg", size?: number) => ({ name, type: "image/jpeg", size });
const pdf = (name = "a.pdf", size?: number) => ({ name, type: "application/pdf", size });

test("the default policy matches the server: 1 MB stored photos, 12 MB incoming, 2 MB PDFs", () => {
  assert.equal(DEFAULT_POLICY.photo_max_stored_kb, 1024);
  assert.equal(DEFAULT_POLICY.photo_max_upload_mb, 12);
  assert.equal(DEFAULT_POLICY.pdf_max_mb, 2);
  assert.equal(DEFAULT_POLICY.max_dimension, 1600);
});

test("one photo, several photos and one PDF are valid selections", () => {
  assert.equal(validateSelection([photo()]), null);
  assert.equal(validateSelection([photo("1.jpg"), photo("2.png"), photo("3.webp")]), null);
  assert.equal(validateSelection([pdf("bill.pdf", 1.5 * MB)]), null);
  assert.equal(validateSelection([]), null);
});

test("a PDF must be alone", () => {
  assert.match(validateSelection([pdf(), photo()]) ?? "", /on its own/);
  assert.match(validateSelection([pdf("a.pdf"), pdf("b.pdf")]) ?? "", /on its own/);
});

test("a PDF over the limit is refused with advice; a small one is fine", () => {
  const msg = validateSelection([pdf("scan.pdf", 2.5 * MB)]) ?? "";
  assert.match(msg, /at most 2 MB/);
  assert.match(msg, /photos of the pages/);
  assert.equal(validateSelection([pdf("ok.pdf", 1.9 * MB)]), null);
  assert.equal(validateSelection([pdf("unknown-size.pdf")]), null);       // the phone did not say: the server decides
});

test("a camera photo of several MB is fine; above the incoming ceiling it is refused", () => {
  assert.equal(validateSelection([photo("IMG.jpg", 4.8 * MB)]), null);    // what the installed app sends today
  assert.match(validateSelection([photo("huge.jpg", 13 * MB)]) ?? "", /more than the 12 MB/);
});

test("other file types and too many files are refused", () => {
  assert.match(validateSelection([{ name: "x.docx", type: "application/msword" }]) ?? "", /JPG, PNG or WEBP photo, or a PDF/);
  assert.match(validateSelection(Array.from({ length: 21 }, (_, i) => photo(`${i}.jpg`))) ?? "", /at most 20/);
});

test("a policy from the server changes the limits (nothing is hard-coded)", () => {
  const strict = { ...DEFAULT_POLICY, pdf_max_mb: 1, photo_max_upload_mb: 1 };
  assert.match(validateSelection([pdf("a.pdf", 1.5 * MB)], strict) ?? "", /at most 1 MB/);
  assert.match(validateSelection([photo("a.jpg", 2 * MB)], strict) ?? "", /more than the 1 MB/);
});

test("the selection is described the way the server will treat it", () => {
  assert.equal(describeSelection([]), "Nothing chosen yet");
  assert.equal(describeSelection([photo()]), "1 photo");
  assert.match(describeSelection([photo(), photo(), photo()]), /3 photos.*merged into one PDF/);
  assert.match(describeSelection([pdf()]), /1 PDF/);
});

test("only a photo that is not already small is shrunk on the phone", () => {
  assert.equal(shouldShrink(photo("a.jpg", 4 * MB)), true);
  assert.equal(shouldShrink(photo("a.jpg", 200 * 1024)), false);          // already small: never compressed twice
  assert.equal(shouldShrink(photo("a.jpg")), true);                        // unknown size: shrink to be safe
  assert.equal(shouldShrink(pdf("a.pdf", 5 * MB)), false);                 // a PDF is never touched
});

test("resizing limits the longest side, never enlarges and keeps the shape", () => {
  assert.deepEqual(fitWithin(4000, 3000, 1600), { width: 1600, height: 1200 });
  assert.deepEqual(fitWithin(3000, 4000, 1600), { width: 1200, height: 1600 });
  assert.deepEqual(fitWithin(800, 600, 1600), { width: 800, height: 600 });
});

test("slot badges read like the web page", () => {
  assert.deepEqual(slotBadge("card", null), { text: "Missing", tone: "neutral" });
  assert.deepEqual(slotBadge("card", {}), { text: "On file", tone: "success" });
  assert.deepEqual(slotBadge("payment", {}), { text: "Paid", tone: "success" });
  assert.deepEqual(slotBadge("bill", { status: "PENDING", overdue: false }), { text: "Pending", tone: "warning" });
  assert.deepEqual(slotBadge("bill", { status: "PENDING", overdue: true }), { text: "Overdue", tone: "danger" });
  assert.deepEqual(slotBadge("bill", { status: "CLEARED" }), { text: "Cleared", tone: "success" });
});

test("a retry of the same files has the same signature; different files do not", () => {
  assert.equal(selectionSignature([{ uri: "file:///a.jpg" }, { uri: "file:///b.jpg" }]), selectionSignature([{ uri: "file:///a.jpg" }, { uri: "file:///b.jpg" }]));
  assert.notEqual(selectionSignature([{ uri: "file:///a.jpg" }]), selectionSignature([{ uri: "file:///c.jpg" }]));
});

test("sizes and months are formatted for people", () => {
  assert.equal(fmtBytes(200 * 1024), "200 KB");
  assert.equal(fmtBytes(1.5 * MB), "1.5 MB");
  assert.match(monthLabel("2026-10"), /October 2026/);
  assert.match(monthLabel("2026-03", false), /Mar 2026/);
});
