import { afterEach, describe, expect, it, vi } from "vitest";
import { apiRequest, ApiError } from "@/services/api";
import { importStoresFile } from "@/services/stores";

afterEach(() => vi.unstubAllGlobals());

describe("network failures", () => {
  it("blames the server, not the user's internet, when the browser is online", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    vi.stubGlobal("navigator", { onLine: true });
    await expect(apiRequest("/x", { silent: true })).rejects.toMatchObject({ status: 0, message: expect.stringContaining("reach the Veekay server") });
  });

  it("says offline only when the browser reports it", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    vi.stubGlobal("navigator", { onLine: false });
    await expect(apiRequest("/x", { silent: true })).rejects.toMatchObject({ status: 0, message: expect.stringContaining("offline") });
  });

  it("announces a burst of failures once", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    vi.stubGlobal("navigator", { onLine: true });
    const { subscribeToasts } = await import("@/lib/toast");
    let count = 0;
    const off = subscribeToasts((t) => (count = t.length));
    await Promise.all(Array.from({ length: 10 }, () => apiRequest("/x").catch(() => undefined)));
    off();
    expect(count).toBeLessThanOrEqual(1);
  });

  it("lets a long server job say what really happened", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(apiRequest("/x", { silent: true, networkErrorMessage: "server stopped" })).rejects.toThrow("server stopped");
  });

  it("store import does not blame the user's internet", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const err = await importStoresFile("blinkit", new File(["x"], "a.csv")).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toMatch(/Nothing was imported/);
    expect(err.message).not.toMatch(/check your (internet )?connection/i);
  });

  it("shows the server's own reason for a refused file", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "The sheet has more than 20,000 rows." }), { status: 422 })));
    await expect(apiRequest("/x", { silent: true })).rejects.toMatchObject({ status: 422, message: "The sheet has more than 20,000 rows." });
  });
});
