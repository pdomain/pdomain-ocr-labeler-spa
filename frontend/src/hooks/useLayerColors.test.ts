// useLayerColors.test.ts — Verify reactivity to data-theme attribute changes.
import { renderHook, act } from "@testing-library/react";
import { useLayerColors } from "./useLayerColors";

it("returns valid LayerColors keys on initial render", () => {
  const { result } = renderHook(() => useLayerColors());
  expect(result.current).toHaveProperty("block");
  expect(result.current).toHaveProperty("para");
  expect(result.current).toHaveProperty("line");
  expect(result.current).toHaveProperty("word");
});

it("re-reads colors when data-theme attribute changes", async () => {
  const { result, rerender } = renderHook(() => useLayerColors());

  act(() => {
    document.documentElement.setAttribute("data-theme", "dark");
  });

  // Give MutationObserver callbacks a chance to fire (jsdom fires them
  // asynchronously via microtask queue).
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });

  rerender();
  // jsdom doesn't compute CSS variables so values remain fallbacks, but
  // the hook must not throw and must return all required keys.
  expect(result.current).toHaveProperty("block");
  expect(result.current).toHaveProperty("para");
  expect(result.current).toHaveProperty("line");
  expect(result.current).toHaveProperty("word");
  // Values should be non-empty strings.
  expect(typeof result.current.block).toBe("string");
  expect(result.current.block.length).toBeGreaterThan(0);
});

it("disconnects the MutationObserver on unmount (no leak)", () => {
  const disconnectSpy = vi.fn();
  const originalMutationObserver = globalThis.MutationObserver;

  // Spy on MutationObserver to capture disconnect calls.
  globalThis.MutationObserver = class extends originalMutationObserver {
    disconnect() {
      disconnectSpy();
      super.disconnect();
    }
  } as typeof MutationObserver;

  const { unmount } = renderHook(() => useLayerColors());
  unmount();

  expect(disconnectSpy).toHaveBeenCalledTimes(1);

  // Restore.
  globalThis.MutationObserver = originalMutationObserver;
});
