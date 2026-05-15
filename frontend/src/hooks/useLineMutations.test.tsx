// useLineMutations.test.tsx — unit tests for line-level mutation hooks.
// Spec: docs/specs/2026-05-12-word-matches-design.md §LineCard header
// Issue #202
//
// Acceptance:
//   - useValidateLine, useCopyLineGt, useDeleteLine are all exported functions
//   - Each hook returns an object with a `mutate` function (TanStack Query shape)

import { describe, it, expect } from "vitest";
import { renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import {
  useValidateLine,
  useCopyLineGt,
  useDeleteLine,
  useUpdateWordGt,
  useMergeLines,
  usePatchParagraph,
} from "./useLineMutations";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return Wrapper;
}

describe("useValidateLine", () => {
  it("is a function", () => {
    expect(typeof useValidateLine).toBe("function");
  });

  it("returns a mutation object with mutate and mutateAsync", () => {
    const Wrapper = makeWrapper();
    const { result } = renderHook(() => useValidateLine("proj1", 0), { wrapper: Wrapper });
    expect(typeof result.current.mutate).toBe("function");
    expect(typeof result.current.mutateAsync).toBe("function");
  });
});

describe("useCopyLineGt", () => {
  it("is a function", () => {
    expect(typeof useCopyLineGt).toBe("function");
  });

  it("returns a mutation object with mutate and mutateAsync", () => {
    const Wrapper = makeWrapper();
    const { result } = renderHook(() => useCopyLineGt("proj1", 0), { wrapper: Wrapper });
    expect(typeof result.current.mutate).toBe("function");
    expect(typeof result.current.mutateAsync).toBe("function");
  });
});

describe("useDeleteLine", () => {
  it("is a function", () => {
    expect(typeof useDeleteLine).toBe("function");
  });

  it("returns a mutation object with mutate and mutateAsync", () => {
    const Wrapper = makeWrapper();
    const { result } = renderHook(() => useDeleteLine("proj1", 0), { wrapper: Wrapper });
    expect(typeof result.current.mutate).toBe("function");
    expect(typeof result.current.mutateAsync).toBe("function");
  });
});

describe("useUpdateWordGt", () => {
  it("is a function", () => {
    expect(typeof useUpdateWordGt).toBe("function");
  });

  it("returns a mutation object with mutate and mutateAsync", () => {
    const Wrapper = makeWrapper();
    const { result } = renderHook(() => useUpdateWordGt("proj1", 0), { wrapper: Wrapper });
    expect(typeof result.current.mutate).toBe("function");
    expect(typeof result.current.mutateAsync).toBe("function");
  });
});

describe("useMergeLines (FO-3)", () => {
  it("is a function", () => {
    expect(typeof useMergeLines).toBe("function");
  });

  it("returns a mutation object with mutate and mutateAsync", () => {
    const Wrapper = makeWrapper();
    const { result } = renderHook(() => useMergeLines("proj1", 0), { wrapper: Wrapper });
    expect(typeof result.current.mutate).toBe("function");
    expect(typeof result.current.mutateAsync).toBe("function");
  });
});

describe("usePatchParagraph (FO-1)", () => {
  it("is a function", () => {
    expect(typeof usePatchParagraph).toBe("function");
  });

  it("returns a mutation object with mutate and mutateAsync", () => {
    const Wrapper = makeWrapper();
    const { result } = renderHook(() => usePatchParagraph("proj1", 0), { wrapper: Wrapper });
    expect(typeof result.current.mutate).toBe("function");
    expect(typeof result.current.mutateAsync).toBe("function");
  });
});
