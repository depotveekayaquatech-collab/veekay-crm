import { afterEach, describe, expect, it, vi } from "vitest";
import { dismissToast, pushToast, subscribeToasts, type Toast } from "@/lib/toast";

function current(): Toast[] {
  let seen: Toast[] = [];
  subscribeToasts((t) => (seen = t))();
  return seen;
}

afterEach(() => {
  current().forEach((t) => dismissToast(t.id));
  vi.useRealTimers();
});

describe("toast bus", () => {
  it("does not stack identical toasts from parallel failures", () => {
    for (let i = 0; i < 12; i++) pushToast("Unable to reach the Veekay server.");
    expect(current()).toHaveLength(1);
  });

  it("caps distinct toasts at three", () => {
    for (let i = 0; i < 6; i++) pushToast(`message ${i}`);
    expect(current().map((t) => t.message)).toEqual(["message 3", "message 4", "message 5"]);
  });

  it("expires a toast after five seconds", () => {
    vi.useFakeTimers();
    pushToast("gone soon");
    vi.advanceTimersByTime(5001);
    expect(current()).toHaveLength(0);
  });
});
