// useLabelVocabulary.test.tsx — unit tests for the useLabelVocabulary hook.
//
// Q-B2-STYLE-LABELS option (b): hook must source canonical vocab from backend.
//
// Contracts:
//   - returns FALLBACK lists before query resolves (never empty palette)
//   - returns server data after query resolves
//   - fallback lists contain no non-canonical values
//   - superscript/subscript are in wordComponents, NOT textStyleLabels
//   - applied values are canonical book-tools strings

import { describe, it, expect } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import React from "react";
import { server } from "../test/server";
import { useLabelVocabulary, FALLBACK_STYLES, FALLBACK_COMPONENTS } from "./useLabelVocabulary";

// Canonical sets from book-tools — frontend-local mirror.
//
// These are a COPY of book-tools' ALLOWED_TEXT_STYLE_LABELS and ALLOWED_COMPONENTS
// (pdomain_book_tools.ocr.label_normalization). The frontend cannot import Python
// source, so this mirror cannot be derived at build time.
//
// AUTHORITATIVE DRIFT GUARD: the backend route test
//   tests/integration/test_label_vocabulary_router.py
// imports ALLOWED_TEXT_STYLE_LABELS / ALLOWED_COMPONENTS live from book-tools and
// asserts the /api/label-vocabulary route returns EXACTLY those sets. That test
// catches any book-tools change before this file does.
//
// If book-tools changes its allowed sets, the backend route test fails first.
// When that happens, update BOTH these mirrors AND the FALLBACK_* arrays in
// useLabelVocabulary.ts to match the new canonical sets.
const CANONICAL_STYLES = new Set([
  "all caps",
  "blackletter",
  "bold",
  "handwritten",
  "italics",
  "monospace",
  "regular",
  "small caps",
  "strikethrough",
  "underline",
]);

const CANONICAL_COMPONENTS = new Set([
  "drop cap",
  "drop cap unrecovered",
  "footnote marker",
  "subscript",
  "superscript",
]);

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: qc }, children);
  };
}

describe("useLabelVocabulary — fallback behavior", () => {
  it("returns non-empty textStyleLabels before query resolves (no empty palette)", () => {
    const { result } = renderHook(() => useLabelVocabulary(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.textStyleLabels.length).toBeGreaterThan(0);
  });

  it("returns non-empty wordComponents before query resolves (no empty palette)", () => {
    const { result } = renderHook(() => useLabelVocabulary(), {
      wrapper: makeWrapper(),
    });
    expect(result.current.wordComponents.length).toBeGreaterThan(0);
  });

  it("FALLBACK_STYLES contains only canonical book-tools values", () => {
    for (const s of FALLBACK_STYLES) {
      expect(CANONICAL_STYLES.has(s)).toBe(true);
    }
  });

  it("FALLBACK_COMPONENTS contains only canonical book-tools values", () => {
    for (const c of FALLBACK_COMPONENTS) {
      expect(CANONICAL_COMPONENTS.has(c)).toBe(true);
    }
  });

  it("superscript is NOT in FALLBACK_STYLES (it is a component, not a style)", () => {
    expect(FALLBACK_STYLES).not.toContain("superscript");
  });

  it("subscript is NOT in FALLBACK_STYLES (it is a component, not a style)", () => {
    expect(FALLBACK_STYLES).not.toContain("subscript");
  });

  it("superscript IS in FALLBACK_COMPONENTS", () => {
    expect(FALLBACK_COMPONENTS).toContain("superscript");
  });

  it("subscript IS in FALLBACK_COMPONENTS", () => {
    expect(FALLBACK_COMPONENTS).toContain("subscript");
  });
});

describe("useLabelVocabulary — server data", () => {
  it("returns server text_style_labels when query resolves", async () => {
    server.use(
      http.get("/api/label-vocabulary", () => {
        return HttpResponse.json({
          text_style_labels: ["bold", "italics"],
          word_components: ["superscript"],
        });
      }),
    );

    const { result } = renderHook(() => useLabelVocabulary(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.textStyleLabels).toEqual(["bold", "italics"]);
  });

  it("returns server word_components when query resolves", async () => {
    server.use(
      http.get("/api/label-vocabulary", () => {
        return HttpResponse.json({
          text_style_labels: ["bold"],
          word_components: ["drop cap", "superscript"],
        });
      }),
    );

    const { result } = renderHook(() => useLabelVocabulary(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.wordComponents).toEqual(["drop cap", "superscript"]);
  });

  it("falls back to FALLBACK_STYLES on server error (no crash, no empty palette)", async () => {
    server.use(
      http.get("/api/label-vocabulary", () => {
        return HttpResponse.json({ detail: "error" }, { status: 500 });
      }),
    );

    const { result } = renderHook(() => useLabelVocabulary(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    // Fallback keeps the palette populated
    expect(result.current.textStyleLabels.length).toBeGreaterThan(0);
    expect(result.current.wordComponents.length).toBeGreaterThan(0);
  });

  it("uses queryKey ['label-vocabulary'] for caching", async () => {
    server.use(
      http.get("/api/label-vocabulary", () => {
        return HttpResponse.json({
          text_style_labels: ["bold"],
          word_components: ["superscript"],
        });
      }),
    );

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children);

    const { result } = renderHook(() => useLabelVocabulary(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const cached = qc.getQueryData<{ text_style_labels: string[]; word_components: string[] }>([
      "label-vocabulary",
    ]);
    expect(cached).toBeTruthy();
    expect(cached?.text_style_labels).toContain("bold");
  });
});
