import { afterEach, describe, expect, it, vi } from "vitest";
import { apiRequest, ApiError } from "@/services/api";
import { importStoresFile } from "@/services/stores";

afterEach(() => vi.unstubAllGlobals());

describe("network failures", () => {
  it("uses the generic message by default", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(apiRequest("/x", { silent: true })).rejects.toMatchObject({ status: 0, message: expect.stringContaining("check your connection") });
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
