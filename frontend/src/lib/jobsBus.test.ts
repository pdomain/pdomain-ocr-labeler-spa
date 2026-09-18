// jobsBus.test.ts — unit tests for the minimal job-touched pub/sub.

import { describe, it, expect, vi } from "vitest";
import { notifyJobsBus, subscribeJobsBus } from "./jobsBus";

describe("jobsBus", () => {
  it("calls every subscribed listener on notify", () => {
    const a = vi.fn();
    const b = vi.fn();
    subscribeJobsBus(a);
    subscribeJobsBus(b);

    notifyJobsBus();

    expect(a).toHaveBeenCalledTimes(1);
    expect(b).toHaveBeenCalledTimes(1);
  });

  it("stops calling a listener after it unsubscribes", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeJobsBus(listener);

    notifyJobsBus();
    unsubscribe();
    notifyJobsBus();

    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("notifying with no subscribers is a harmless no-op", () => {
    expect(() => {
      notifyJobsBus();
    }).not.toThrow();
  });
});
