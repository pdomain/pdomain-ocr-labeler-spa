// Vitest global setup — loaded once per test file via `setupFiles` in
// vitest.config.ts. Registers @testing-library/jest-dom matchers
// (e.g. `toBeInTheDocument`) and wires the msw lifecycle so handlers reset
// between tests and unhandled requests fail loudly.
import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./server";

// jsdom does not implement ResizeObserver. Components that use it (e.g. canvas
// overlays) would throw `ReferenceError: ResizeObserver is not defined` without
// this stub. Tests that need a size measurement should mock
// `Element.prototype.getBoundingClientRect` and invoke the observer callback
// manually.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
if (typeof globalThis.ResizeObserver === "undefined") {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
}

// jsdom does not implement EventSource. Components using SSE would throw at
// mount time without this stub. Tests that need real SSE event dispatch should
// override globalThis.EventSource with their own mock via vi.stubGlobal.
class EventSourceStub {
  addEventListener(_type: string, _fn: unknown): void {}
  removeEventListener(_type: string, _fn: unknown): void {}
  close(): void {}
}
if (typeof globalThis.EventSource === "undefined") {
  (globalThis as unknown as { EventSource: unknown }).EventSource = EventSourceStub;
}

// Start the mock server before any test runs, with strict unhandled-request
// mode so missing handlers cause test failures rather than silent bypasses.
beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
});

// Reset any per-test handlers (added with `server.use(...)`) so a leak
// in one test can't contaminate the next.
afterEach(() => {
  server.resetHandlers();
});

// Tear down once the suite finishes.
afterAll(() => {
  server.close();
});
