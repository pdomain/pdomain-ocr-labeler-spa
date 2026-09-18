// ProjectPage.matchesPaneWiring.test.tsx — Matches-pane (WordMatchView) handler wiring.
//
// Before this fix, ProjectPage mounted WordMatchView with only `lines`,
// `filter`, `onEditWord`, and `onSelectLine`. `onValidate`, `onDelete`,
// `onCopyGtToOcr`, `onCopyOcrToGt`, and `onCommitGt` were never passed —
// LineCard/WordCell declare them as optional and call them with `?.()`, so
// every Validate/Delete/GT→OCR/OCR→GT button and the inline per-word GT
// input silently no-op'd in the Matches pane.
//
// Strategy: mock WordMatchView to capture the props ProjectPage passes (the
// established pattern in ProjectPage.editWord.test.tsx / ProjectPage.rebox.test.tsx
// — the real WordMatchView renders through @tanstack/react-virtual, which
// mounts no rows under jsdom's zero-layout viewport, documented in
// WordMatchView.test.tsx). Capturing and invoking the prop exercises the
// exact handler ProjectPage constructs and wires to the real mutations —
// the same mutations LineDetail.tsx uses for its embedded LineCard.

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { server } from "../test/server";
import { ROUTES } from "../lib/routes";
import { dialogStore } from "../stores/dialog-store";
import { useUiPrefs } from "../stores/ui-prefs";
import { clearSelection } from "../stores/selection-store";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mockNavigate };
});

// ─── Capture every prop ProjectPage passes to WordMatchView ────────────────

interface CapturedProps {
  onValidate?: (lineIndex: number, validated: boolean) => void;
  onCopyGtToOcr?: (lineIndex: number) => void;
  onCopyOcrToGt?: (lineIndex: number) => void;
  onDelete?: (lineIndex: number) => void;
  onCommitGt?: (wordId: string, lineIndex: number, wordIndex: number, text: string) => void;
}
let captured: CapturedProps = {};

vi.mock("../components/WordMatchView", () => ({
  __esModule: true,
  WordMatchView: (props: CapturedProps) => {
    captured = props;
    return <div data-testid="word-match-view-stub" />;
  },
}));

// Mock canvas/konva pieces so the rest of the shell mounts cheaply — same
// stubs used across the other ProjectPage.*.test.tsx files.
vi.mock("@pdomain/pdomain-ui/canvas", () => ({
  rectToDisplay: (
    bbox: { x: number; y: number; width: number; height: number },
    encoded: { scale: number },
  ) => ({
    x: bbox.x * encoded.scale,
    y: bbox.y * encoded.scale,
    width: bbox.width * encoded.scale,
    height: bbox.height * encoded.scale,
  }),
  rectItemsToDisplay: <T extends { bbox: { x: number; y: number; width: number; height: number } }>(
    items: T[],
    encoded: { scale: number } | null,
  ) =>
    encoded
      ? items.map((item) => ({
          ...item,
          bbox: {
            x: item.bbox.x * encoded.scale,
            y: item.bbox.y * encoded.scale,
            width: item.bbox.width * encoded.scale,
            height: item.bbox.height * encoded.scale,
          },
        }))
      : items,
  RectOverlayLayer: ({
    layer,
    items,
    dimmed,
  }: {
    layer: string;
    items: Array<{ id: string }>;
    dimmed?: boolean;
  }) => (
    <div
      data-testid={`bbox-overlay-${layer}`}
      data-item-count={items.length}
      data-dimmed={dimmed ? "true" : undefined}
    />
  ),
  PageImageCanvas: ({
    children,
  }: {
    children?: {
      selection?: (p: Record<string, unknown>) => React.ReactNode;
      tool?: (p: Record<string, unknown>) => React.ReactNode;
    };
  }) => (
    <div data-testid="pdomain-image-canvas">
      {children?.selection?.({})}
      {children?.tool?.({})}
    </div>
  ),
}));

vi.mock("react-konva", () => ({
  Stage: ({
    children,
    width,
    height,
    "data-testid": tid,
  }: {
    children?: React.ReactNode;
    width?: number;
    height?: number;
    "data-testid"?: string;
  }) => (
    <div data-testid={tid ?? "konva-stage"} data-width={width} data-height={height}>
      {children}
    </div>
  ),
  Layer: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Rect: () => <div data-testid="konva-rect" />,
  Image: () => <div data-testid="konva-image" />,
}));

vi.mock("use-image", () => ({
  __esModule: true,
  default: () => [null, "loaded"],
}));

import ProjectPage from "./ProjectPage";

// ─── Helpers ────────────────────────────────────────────────────────────────

function renderProjectPage(path = "/projects/p1/pages/pageno/1") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={ROUTES.PROJECT_PAGE_NO} element={<ProjectPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function projectFixture() {
  return {
    project: {
      project_id: "p1",
      project_root: "/data/p1",
      image_paths: ["page_001.png"],
      ground_truth_map: {},
    },
    current_page_index: 0,
    generation: 1,
  };
}

function pageFixture() {
  return {
    project_id: "p1",
    page_index: 0,
    page_record: {
      page_index: 0,
      page_number: 1,
      image_path: "/data/p1/page_001.png",
      page_source: "ocr",
      ocr_failed: false,
      rotation_degrees: 0,
      rotation_source: null,
    },
    line_matches: [
      {
        line_index: 0,
        paragraph_index: 0,
        ocr_line_text: "hello",
        ground_truth_line_text: "hello",
        overall_match_status: "mismatch",
        exact_count: 0,
        fuzzy_count: 0,
        mismatch_count: 1,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: 1,
        is_fully_validated: false,
        word_matches: [
          {
            line_index: 0,
            word_index: 0,
            ocr_text: "hello",
            ground_truth_text: "hallo",
            match_status: "mismatch",
            fuzz_score: 0.8,
            normalized_match: false,
            is_validated: false,
            text_style_labels: [],
            word_components: [],
            bbox: { x: 0, y: 0, width: 10, height: 10 },
            word_id: "w-0-0",
          },
        ],
      },
    ],
    selection: {
      selection_mode: "paragraph",
      selected_paragraphs: [],
      selected_lines: [],
      selected_words: [],
    },
    encoded_dims: {
      src_width: 1600,
      src_height: 1200,
      display_width: 800,
      display_height: 600,
      scale: 0.5,
    },
    line_filter: "all",
    image_url: "/api/projects/p1/image/0",
    generation: 1,
    page_text_ocr: "hello",
    page_text_gt: "hallo",
    extra: {},
  };
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("ProjectPage — Matches pane (WordMatchView) handler wiring", () => {
  beforeEach(() => {
    captured = {};
    dialogStore.reset();
    mockNavigate.mockReset();
    clearSelection();
    useUiPrefs.setState({ drawerOpen: true, rightPanelOpen: true });
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", () => HttpResponse.json(pageFixture())),
      http.post("/api/projects/:pid/current-page-index", () => HttpResponse.json({})),
    );
  });

  async function renderAndWaitForCaptured() {
    renderProjectPage();
    await screen.findByTestId("project-page");
    await waitFor(() => {
      expect(typeof captured.onValidate).toBe("function");
      expect(typeof captured.onCopyGtToOcr).toBe("function");
      expect(typeof captured.onCopyOcrToGt).toBe("function");
      expect(typeof captured.onDelete).toBe("function");
      expect(typeof captured.onCommitGt).toBe("function");
    });
  }

  it("passes onValidate and it POSTs words/validate-batch scope=line", async () => {
    const calls: { url: string; body: unknown }[] = [];
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/validate-batch", async ({ request }) => {
        calls.push({ url: request.url, body: await request.json() });
        return HttpResponse.json(pageFixture());
      }),
    );
    await renderAndWaitForCaptured();

    act(() => {
      captured.onValidate?.(0, true);
    });

    await waitFor(() => {
      expect(calls.length).toBe(1);
    });
    expect(calls[0]!.url).toContain("/words/validate-batch");
    expect(calls[0]!.body).toEqual(
      expect.objectContaining({ scope: "line", line_indices: [0], validated: true }),
    );
  });

  it("passes onCopyGtToOcr and it POSTs lines/{li}/copy-gt direction=gt_to_ocr", async () => {
    const calls: { url: string; body: unknown }[] = [];
    server.use(
      http.post("/api/projects/:pid/pages/:idx/lines/:li/copy-gt", async ({ request }) => {
        calls.push({ url: request.url, body: await request.json() });
        return HttpResponse.json(pageFixture());
      }),
    );
    await renderAndWaitForCaptured();

    act(() => {
      captured.onCopyGtToOcr?.(0);
    });

    await waitFor(() => {
      expect(calls.length).toBe(1);
    });
    expect(calls[0]!.url).toContain("/lines/0/copy-gt");
    expect(calls[0]!.body).toEqual(expect.objectContaining({ direction: "gt_to_ocr" }));
  });

  it("passes onCopyOcrToGt and it POSTs lines/{li}/copy-gt direction=ocr_to_gt", async () => {
    const calls: { url: string; body: unknown }[] = [];
    server.use(
      http.post("/api/projects/:pid/pages/:idx/lines/:li/copy-gt", async ({ request }) => {
        calls.push({ url: request.url, body: await request.json() });
        return HttpResponse.json(pageFixture());
      }),
    );
    await renderAndWaitForCaptured();

    act(() => {
      captured.onCopyOcrToGt?.(0);
    });

    await waitFor(() => {
      expect(calls.length).toBe(1);
    });
    expect(calls[0]!.url).toContain("/lines/0/copy-gt");
    expect(calls[0]!.body).toEqual(expect.objectContaining({ direction: "ocr_to_gt" }));
  });

  // F-035: destructive — must confirm first, same as the D-key hotkey for
  // this same pane (onDelete in useMatchesHotkeys, this file's sibling
  // ProjectPage.test.tsx "an action hotkey" describe block covers V; there
  // is no existing D-key POST test to duplicate against, so this is the
  // first one covering the confirm→mutate path for the Matches pane).
  it("passes onDelete which opens a confirm dialog before POSTing lines/delete-batch", async () => {
    const calls: { url: string; body: unknown }[] = [];
    server.use(
      http.post("/api/projects/:pid/pages/:idx/lines/delete-batch", async ({ request }) => {
        calls.push({ url: request.url, body: await request.json() });
        return HttpResponse.json(pageFixture());
      }),
    );
    await renderAndWaitForCaptured();

    act(() => {
      captured.onDelete?.(0);
    });

    // Confirm dialog opens; the mutation has not fired yet.
    await waitFor(() => {
      expect(dialogStore.getState().confirm.open).toBe(true);
    });
    expect(dialogStore.getState().confirm.title).toBe("Delete line?");
    expect(calls.length).toBe(0);

    const confirmButton = await screen.findByTestId("confirm-dialog-confirm");
    act(() => {
      confirmButton.click();
    });

    await waitFor(() => {
      expect(calls.length).toBe(1);
    });
    expect(calls[0]!.url).toContain("/lines/delete-batch");
    expect(calls[0]!.body).toEqual(expect.objectContaining({ scope: "line", line_indices: [0] }));
  });

  // This is the one a person would notice: editing a word's ground truth in
  // the Matches pane, blurring the field, and having it silently discarded.
  it("passes onCommitGt and it POSTs words/{li}/{wi}/gt with the new text", async () => {
    const calls: { url: string; body: unknown }[] = [];
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/:li/:wi/gt", async ({ request }) => {
        calls.push({ url: request.url, body: await request.json() });
        return HttpResponse.json(pageFixture().word_matches ?? {});
      }),
    );
    await renderAndWaitForCaptured();

    act(() => {
      captured.onCommitGt?.("w-0-0", 0, 0, "corrected text");
    });

    await waitFor(() => {
      expect(calls.length).toBe(1);
    });
    expect(calls[0]!.url).toContain("/words/0/0/gt");
    expect(calls[0]!.body).toEqual({ text: "corrected text" });
  });

  it("onCommitGt ignores the word_id argument — same (line, word) index contract as LineDetail", async () => {
    // LineDetail's own onCommitGt handler discards the word_id argument too
    // (`(_wordId, li, wi, text) => updateWordGt.mutate({ lineIndex: li,
    // wordIndex: wi, text })`) — the backend route addresses the word by
    // line/word index, not word_id. A mismatched/empty word_id must not
    // change the request.
    const calls: { url: string; body: unknown }[] = [];
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/:li/:wi/gt", async ({ request }) => {
        calls.push({ url: request.url, body: await request.json() });
        return HttpResponse.json(pageFixture().word_matches ?? {});
      }),
    );
    await renderAndWaitForCaptured();

    act(() => {
      captured.onCommitGt?.("", 0, 0, "");
    });

    await waitFor(() => {
      expect(calls.length).toBe(1);
    });
    expect(calls[0]!.url).toContain("/words/0/0/gt");
    // Empty text is passed through unconditionally, matching LineDetail's
    // path — WordCell/LineCard (shared by both surfaces) already gate on
    // "value actually changed at blur", not on emptiness.
    expect(calls[0]!.body).toEqual({ text: "" });
  });
});
