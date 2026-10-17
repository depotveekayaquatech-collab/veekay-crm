import { describe, expect, it } from "vitest";
import { DEFAULT_POLICY, UploadRejected, policyHint, prepareMany, prepareUpload, type Compress } from "@/lib/uploads";

const KB = 1024;
const MB = 1024 * 1024;
const file = (name: string, type: string, bytes: number) => new File([new Uint8Array(bytes)], name, { type });
const p = DEFAULT_POLICY;

describe("upload rules (mirror of the server policy)", () => {
  it("the defaults are 1 MB photos, 2 MB PDFs and 1600 px", () => {
    expect([p.photoMaxStoredKb, p.pdfMaxMb, p.maxDimension]).toEqual([1024, 2, 1600]);
    expect(policyHint(p)).toContain("2 MB");
  });

  it("a PDF is passed through untouched when it is within the limit and refused with advice when it is not", async () => {
    const ok = file("bill.pdf", "application/pdf", 1.5 * MB);
    expect(await prepareUpload(ok, p)).toBe(ok);
    const big = file("scan.pdf", "application/pdf", 2.5 * MB);
    await expect(prepareUpload(big, p)).rejects.toThrow(/at most 2 MB.*photos of the pages/);
    await expect(prepareUpload(big, p)).rejects.toBeInstanceOf(UploadRejected);
  });

  it("a small photo is sent as it is: it is never compressed twice", async () => {
    let called = 0;
    const compress: Compress = async (f) => { called++; return f; };
    const small = file("a.jpg", "image/jpeg", 200 * KB);
    expect(await prepareUpload(small, p, compress)).toBe(small);
    expect(called).toBe(0);
  });

  it("a large photo is shrunk, and the shrunk copy is used only if it is actually smaller", async () => {
    const big = file("photo.jpg", "image/jpeg", 4 * MB);
    const smaller = file("photo.jpg", "image/jpeg", 300 * KB);
    expect(await prepareUpload(big, p, async () => smaller)).toBe(smaller);
    const bigger = file("photo.jpg", "image/jpeg", 5 * MB);
    expect(await prepareUpload(big, p, async () => bigger)).toBe(big);
  });

  it("if shrinking fails in the browser the original goes to the server, which shrinks it itself", async () => {
    const big = file("photo.jpg", "image/jpeg", 4 * MB);
    expect(await prepareUpload(big, p, async () => { throw new Error("no canvas"); })).toBe(big);
  });

  it("refuses other file types and files above what the server accepts, with a clear message", async () => {
    await expect(prepareUpload(file("x.exe", "application/octet-stream", 10 * KB), p)).rejects.toThrow(/JPG, PNG or WEBP photo, or a PDF/);
    await expect(prepareUpload(file("huge.jpg", "image/jpeg", 13 * MB), p)).rejects.toThrow(/12 MB the server accepts/);
  });

  it("several files: the good ones go through and each problem is reported, nothing is lost silently", async () => {
    const { ok, problems } = await prepareMany(
      [file("a.jpg", "image/jpeg", 100 * KB), file("big.pdf", "application/pdf", 3 * MB), file("b.png", "image/png", 90 * KB)], p, async (f) => f,
    );
    expect(ok.map((f) => f.name)).toEqual(["a.jpg", "b.png"]);
    expect(problems).toHaveLength(1);
    expect(problems[0]).toContain("big.pdf");
  });
});
