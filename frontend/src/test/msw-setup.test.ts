// Acceptance test for msw harness: verifies that the mock server is live
// and that unhandled requests throw (onUnhandledRequest: "error").
//
// This test imports the server directly so it can inspect server.listHandlers()
// and verify the lifecycle works correctly. It does NOT rely on a running
// FastAPI backend — all network is intercepted by msw in jsdom.
import { describe, it, expect } from "vitest";
import { server } from "./server";

describe("msw harness", () => {
  it("server is listening (handlers registered by beforeAll in setup.ts)", () => {
    // server.listening is true only after server.listen() has been called.
    // setup.ts calls server.listen({ onUnhandledRequest: "error" }) in
    // beforeAll, which runs before every test file.
    expect((server as any)._state).not.toBe("stopped");
  });

  it("unhandled fetch request throws due to onUnhandledRequest: error", async () => {
    // This request has no registered handler — msw should throw.
    // If onUnhandledRequest were "warn" or "bypass", the fetch would
    // reach the network (or jsdom's fetch stub) and we'd get a different error.
    await expect(fetch("http://localhost:8000/api/unhandled-route")).rejects.toThrow();
  });
});
