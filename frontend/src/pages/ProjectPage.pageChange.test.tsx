// ProjectPage.pageChange.test.tsx — whole-branch review defect 2 (region), and
// P2-SELECTION-PAGE (block/para/line/word).
//
// Region: selecting a proposal or a confirmed region, then navigating to
// another page, must clear that region-level selection — otherwise a hotkey
// fires against the new page's URL carrying the old page's id. That fix
// clears the region selection outright on any page change; it is unaffected
// by P2-SELECTION-PAGE below and is tested first, unchanged.
//
// P2-SELECTION-PAGE: a block/para/line/word selection carries the page index
// it was made on (`selectionStore`'s `SelectionPath.pageIndex`). Navigating
// away does NOT clear it — the raw store still holds it — but it no longer
// resolves against a page other than the one it was made on: the right
// panel and breadcrumb show no selection, and a keyboard action (Alt-arrows)
// on it is a no-op. Returning to the original page resolves it again,
// unaffected by the trip. This intentionally supersedes this file's old pin
// that a line selection was untouched by ANY page-change behavior — it now
// is, just not by clearing.
//
// Unlike ProjectPage.test.tsx, this file does NOT mock react-router-dom's
// useNavigate — real navigation is what exercises the pageIndex change this
// fix reacts to. `nav-next-button` (ProjectNavigationControls) drives it.

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { server } from "../test/server";
import { ROUTES } from "../lib/routes";
import { dialogStore } from "../stores/dialog-store";
import { useUiPrefs } from "../stores/ui-prefs";
import {
  clearSelection,
  selectionStore,
  selectLine,
  selectWord,
  selectPara,
  selectProposal,
  selectRegion,
} from "../stores/selection-store";
import {
  reviewSelectionIntentStore,
  setReviewSelectionIntent,
} from "../stores/review-selection-intent-store";
import type { components } from "../api/types";

type RegionView = components["schemas"]["RegionView"];

// ─── Mocks (mirrors ProjectPage.test.tsx's canvas stack — same reasons) ────
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
    page,
    children,
  }: {
    src?: string;
    page?: { width: number; height: number };
    words?: unknown[];
    children?: {
      selection?: (p: Record<string, unknown>) => React.ReactNode;
      tool?: (p: Record<string, unknown>) => React.ReactNode;
    };
  }) => (
    <div
      data-testid="image-viewport"
      data-width={page?.width}
      data-height={page?.height}
      tabIndex={0}
    >
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

// Import AFTER mocks so the page pulls them.
import ProjectPage from "./ProjectPage";

// ─── Helpers ────────────────────────────────────────────────────────────────

function renderProjectPage(path = "/projects/p1/pages/pageno/1") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
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
    project_id: "p1",
    project_root: "/data/p1",
    image_paths: ["page_001.png", "page_002.png"],
    ground_truth_map: {},
  };
}

function proposalRegion(proposal_id: string): RegionView {
  return {
    region_id: null,
    proposal_id,
    role: "paragraph",
    box: { x: 0, y: 0, width: 10, height: 10 },
    confirmed: false,
    confidence: 0.9,
    stale: false,
  };
}

function pageFixture(idx: number) {
  return {
    project_id: "p1",
    page_index: idx,
    line_matches: [
      {
        line_index: 3,
        paragraph_index: 0,
        overall_match_status: "exact",
        is_fully_validated: true,
        validated_word_count: 0,
        total_word_count: 1,
        word_matches: [
          {
            line_index: 3,
            word_index: 0,
            ocr_text: "w",
            ground_truth_text: "w",
            match_status: "exact",
            normalized_match: false,
            is_validated: false,
            bbox: { x: 0, y: 0, width: 1, height: 1 },
          },
        ],
      },
    ],
    line_filter: "all",
    image_url: `/api/projects/p1/image/${String(idx)}`,
    generation: 1,
    regions: [proposalRegion("prop-1")],
  };
}

describe("ProjectPage — region selection is scoped to its page (defect 2)", () => {
  beforeEach(() => {
    dialogStore.reset();
    clearSelection();
    reviewSelectionIntentStore.setState({ intent: null });
    useUiPrefs.setState({ drawerOpen: true, rightPanelOpen: true });
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", ({ params }) => {
        const idx = Number(params["idx"]);
        return HttpResponse.json(pageFixture(idx));
      }),
    );
  });

  afterEach(() => {
    reviewSelectionIntentStore.setState({ intent: null });
  });

  it("clears a selected proposal when the page index changes", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    selectProposal("prop-1");
    expect(selectionStore.getState().level).toBe("region");

    const nextButton = await screen.findByTestId("nav-next-button");
    await waitFor(() => expect(nextButton).not.toBeDisabled());
    fireEvent.click(nextButton);

    await waitFor(() => expect(screen.getByTestId("nav-page-input")).toHaveValue(2));
    expect(selectionStore.getState().level).toBe("none");
    expect(selectionStore.getState().path).toEqual({});
  });

  it("clears a selected confirmed region when the page index changes", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    selectRegion("region-1");
    expect(selectionStore.getState().level).toBe("region");

    const nextButton = await screen.findByTestId("nav-next-button");
    await waitFor(() => expect(nextButton).not.toBeDisabled());
    fireEvent.click(nextButton);

    await waitFor(() => expect(screen.getByTestId("nav-page-input")).toHaveValue(2));
    expect(selectionStore.getState().level).toBe("none");
  });

  it("does NOT clear a line selection when the page index changes (P2-SELECTION-PAGE: it resolves as empty instead — see the describe block below)", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    selectLine(0, 3);
    expect(selectionStore.getState().level).toBe("line");
    expect(selectionStore.getState().path).toEqual({ pageIndex: 0, lineId: 3 });

    const nextButton = await screen.findByTestId("nav-next-button");
    await waitFor(() => expect(nextButton).not.toBeDisabled());
    fireEvent.click(nextButton);

    await waitFor(() => expect(screen.getByTestId("nav-page-input")).toHaveValue(2));
    // The raw store is untouched by the page change — this fix does not clear
    // it, unlike the region-level fix above.
    expect(selectionStore.getState().level).toBe("line");
    expect(selectionStore.getState().path).toEqual({ pageIndex: 0, lineId: 3 });
  });
});

// ─── P2-SELECTION-PAGE: block/para/line/word selections carry their page ──
// A selection made on one page must not resolve against a different page
// once loaded — the right panel and breadcrumb must show no selection, and
// a keyboard action on it must do nothing. Returning to the original page
// restores it. `pageFixture` above returns the SAME line/word/paragraph
// indices for every page index, so an unfixed resolver would show identical,
// wrong content on page 2 — exactly the silent defect the issue describes.

describe("ProjectPage — a block/para/line/word selection is scoped to its page (P2-SELECTION-PAGE)", () => {
  beforeEach(() => {
    dialogStore.reset();
    clearSelection();
    reviewSelectionIntentStore.setState({ intent: null });
    useUiPrefs.setState({ drawerOpen: true, rightPanelOpen: true });
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", ({ params }) => {
        const idx = Number(params["idx"]);
        return HttpResponse.json(pageFixture(idx));
      }),
    );
  });

  async function goToPageTwo() {
    const nextButton = await screen.findByTestId("nav-next-button");
    await waitFor(() => expect(nextButton).not.toBeDisabled());
    fireEvent.click(nextButton);
    await waitFor(() => expect(screen.getByTestId("nav-page-input")).toHaveValue(2));
  }

  async function goBackToPageOne() {
    const prevButton = await screen.findByTestId("nav-prev-button");
    await waitFor(() => expect(prevButton).not.toBeDisabled());
    fireEvent.click(prevButton);
    await waitFor(() => expect(screen.getByTestId("nav-page-input")).toHaveValue(1));
  }

  it("a line selection made on one page is not resolved on another, and returning restores it", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    selectLine(0, 3);
    expect(await screen.findByTestId("line-detail-structure-box")).toBeInTheDocument();

    await goToPageTwo();

    // Still there underneath, just not resolved against page 2's (identical)
    // line 3 — the right panel shows no selection instead.
    expect(selectionStore.getState().path).toEqual({ pageIndex: 0, lineId: 3 });
    expect(screen.queryByTestId("line-detail")).not.toBeInTheDocument();
    expect(screen.getByTestId("right-panel-body")).toHaveAttribute("data-level", "none");
    expect(screen.queryByTestId("breadcrumb-chip-line")).not.toBeInTheDocument();

    // A keyboard action on it does nothing while it belongs to another page.
    fireEvent.keyDown(document, { key: "ArrowUp", altKey: true });
    expect(selectionStore.getState().path).toEqual({ pageIndex: 0, lineId: 3 });

    await goBackToPageOne();

    expect(await screen.findByTestId("line-detail-structure-box")).toBeInTheDocument();
  });

  it("a word selection made on one page is not resolved on another, and returning restores it", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    selectWord(0, 3, 0);
    expect(await screen.findByTestId("word-detail")).toBeInTheDocument();
    expect(screen.queryByTestId("right-panel-word-empty")).not.toBeInTheDocument();

    await goToPageTwo();

    expect(selectionStore.getState().path).toEqual({
      pageIndex: 0,
      lineId: 3,
      wordId: [3, 0],
    });
    expect(screen.getByTestId("right-panel-body")).toHaveAttribute("data-level", "none");
    expect(screen.queryByTestId("breadcrumb-chip-word")).not.toBeInTheDocument();

    // A keyboard action (word-level sibling walk) does nothing off-page.
    fireEvent.keyDown(document, { key: "ArrowLeft", altKey: true });
    expect(selectionStore.getState().path).toEqual({
      pageIndex: 0,
      lineId: 3,
      wordId: [3, 0],
    });

    await goBackToPageOne();

    expect(await screen.findByTestId("word-detail")).toBeInTheDocument();
    expect(screen.queryByTestId("right-panel-word-empty")).not.toBeInTheDocument();
  });

  it("a paragraph selection made on one page is not resolved on another, and returning restores it", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    selectPara(0, 0);
    expect(await screen.findByTestId("paragraph-detail")).toBeInTheDocument();
    expect(screen.queryByTestId("right-panel-para-empty")).not.toBeInTheDocument();

    await goToPageTwo();

    expect(selectionStore.getState().path).toEqual({ pageIndex: 0, paraId: 0 });
    expect(screen.getByTestId("right-panel-body")).toHaveAttribute("data-level", "none");
    expect(screen.queryByTestId("breadcrumb-chip-para")).not.toBeInTheDocument();

    // A keyboard action (walk up a level) does nothing off-page.
    fireEvent.keyDown(document, { key: "ArrowUp", altKey: true });
    expect(selectionStore.getState().path).toEqual({ pageIndex: 0, paraId: 0 });

    await goBackToPageOne();

    expect(await screen.findByTestId("paragraph-detail")).toBeInTheDocument();
    expect(screen.queryByTestId("right-panel-para-empty")).not.toBeInTheDocument();
  });
});

// ─── Book review queue design: the '['/']' selection intent survives the
// page-change region clear ────────────────────────────────────────────────
// Design: docs/specs/2026-09-17-book-review-queue-design.md
//   "Selecting after navigation needs an intent, not a direct call".
//
// These tests set the intent directly (rather than pressing ']') because
// the navigation itself is already covered by useRegionReviewHotkeys.test.tsx
// — what matters here is effect ordering on ProjectPage: the page-change
// clear above must not undo the selection this intent makes once the
// destination page's payload arrives.

describe("ProjectPage — the review-queue selection intent survives the page-change clear", () => {
  beforeEach(() => {
    dialogStore.reset();
    clearSelection();
    reviewSelectionIntentStore.setState({ intent: null });
    useUiPrefs.setState({ drawerOpen: true, rightPanelOpen: true });
    server.use(
      http.get("/api/projects/:pid", () => HttpResponse.json(projectFixture())),
      http.get("/api/projects/:pid/pages/:idx", ({ params }) => {
        const idx = Number(params["idx"]);
        return HttpResponse.json(pageFixture(idx));
      }),
    );
  });

  afterEach(() => {
    reviewSelectionIntentStore.setState({ intent: null });
  });

  it("selects the intent's proposal once the destination page loads, surviving the page-change clear", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    // A pre-existing region selection so the page-change clear (which only
    // acts when level === "region") has something to actually clear —
    // proving the intent's later selection isn't a no-op survivor.
    selectProposal("prop-1");
    setReviewSelectionIntent({ pageIndex: 1, proposalId: "prop-1" });

    const nextButton = await screen.findByTestId("nav-next-button");
    await waitFor(() => expect(nextButton).not.toBeDisabled());
    fireEvent.click(nextButton);

    await waitFor(() => expect(screen.getByTestId("nav-page-input")).toHaveValue(2));
    await waitFor(() => expect(selectionStore.getState().path.proposalId).toBe("prop-1"));
    expect(reviewSelectionIntentStore.getState().intent).toBeNull();
  });

  it("survives the clear even when the destination page's payload is already cached (same-commit ordering)", async () => {
    // Visit page 2 once so its payload lands in the QueryClient cache, then
    // return to page 1 — this is the case the ordering comment calls out:
    // navigating back to page 2 a second time resolves `usePage` from cache
    // in the SAME render as the idx0 change, so both the page-change clear
    // effect and the intent-consuming effect below it run in one commit
    // rather than across two (fresh-load) renders. If the clear effect ran
    // *after* the intent effect, it would wipe the selection made here.
    renderProjectPage();
    await screen.findByTestId("project-page");

    const nextButton = await screen.findByTestId("nav-next-button");
    await waitFor(() => expect(nextButton).not.toBeDisabled());
    fireEvent.click(nextButton);
    await waitFor(() => expect(screen.getByTestId("nav-page-input")).toHaveValue(2));

    const prevButton = await screen.findByTestId("nav-prev-button");
    await waitFor(() => expect(prevButton).not.toBeDisabled());
    fireEvent.click(prevButton);
    await waitFor(() => expect(screen.getByTestId("nav-page-input")).toHaveValue(1));

    selectProposal("prop-1");
    expect(selectionStore.getState().level).toBe("region");
    setReviewSelectionIntent({ pageIndex: 1, proposalId: "prop-1" });

    fireEvent.click(await screen.findByTestId("nav-next-button"));

    await waitFor(() => expect(screen.getByTestId("nav-page-input")).toHaveValue(2));
    await waitFor(() => expect(selectionStore.getState().path.proposalId).toBe("prop-1"));
    expect(reviewSelectionIntentStore.getState().intent).toBeNull();
  });

  it("clears an intent whose proposal is absent from the loaded page, selecting nothing", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    setReviewSelectionIntent({ pageIndex: 1, proposalId: "not-on-page-2" });

    const nextButton = await screen.findByTestId("nav-next-button");
    await waitFor(() => expect(nextButton).not.toBeDisabled());
    fireEvent.click(nextButton);

    await waitFor(() => expect(screen.getByTestId("nav-page-input")).toHaveValue(2));
    await waitFor(() => expect(reviewSelectionIntentStore.getState().intent).toBeNull());
    expect(selectionStore.getState().level).toBe("none");
  });

  // Finding 1 (medium, ProjectPage.tsx ~line 412): the intent was only ever
  // consumed when idx0 happened to equal intent.pageIndex, and was never
  // cleared otherwise. An intent set by ']' for a distant page survived any
  // number of *ordinary* page changes that didn't land on it — so later
  // reaching that page through normal navigation would silently auto-select
  // a proposal the user never asked for there.
  it("clears an intent abandoned by intervening ordinary navigation, so later reaching that page does not auto-select", async () => {
    server.use(
      http.get("/api/projects/:pid", () =>
        HttpResponse.json({ ...projectFixture(), image_paths: ["p1.png", "p2.png", "p3.png"] }),
      ),
    );
    renderProjectPage();
    await screen.findByTestId("project-page");
    // Simulates ']' recording an intent for page index 2 (the 3rd page) from
    // page index 0 — the destination is not adjacent, so ordinary next/prev
    // navigation passes through page index 1 first.
    setReviewSelectionIntent({ pageIndex: 2, proposalId: "prop-1" });

    const nextButton = await screen.findByTestId("nav-next-button");
    await waitFor(() => expect(nextButton).not.toBeDisabled());
    fireEvent.click(nextButton); // idx0: 0 -> 1, does not match the intent's pageIndex (2).

    await waitFor(() => expect(screen.getByTestId("nav-page-input")).toHaveValue(2));
    await waitFor(() => expect(reviewSelectionIntentStore.getState().intent).toBeNull());

    fireEvent.click(await screen.findByTestId("nav-next-button")); // idx0: 1 -> 2, ordinary arrival.

    await waitFor(() => expect(screen.getByTestId("nav-page-input")).toHaveValue(3));
    expect(selectionStore.getState().path.proposalId).toBeUndefined();
  });

  it("does not clear the intent set for the destination the same navigation is heading to", async () => {
    renderProjectPage();
    await screen.findByTestId("project-page");
    setReviewSelectionIntent({ pageIndex: 1, proposalId: "prop-1" });

    const nextButton = await screen.findByTestId("nav-next-button");
    await waitFor(() => expect(nextButton).not.toBeDisabled());
    fireEvent.click(nextButton); // idx0: 0 -> 1, matches the intent's own pageIndex.

    await waitFor(() => expect(screen.getByTestId("nav-page-input")).toHaveValue(2));
    await waitFor(() => expect(selectionStore.getState().path.proposalId).toBe("prop-1"));
    expect(reviewSelectionIntentStore.getState().intent).toBeNull();
  });
});
