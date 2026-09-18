// BBoxSection.test.tsx — Tests for Slice 16 bounding-box editor + P3.a (Gaps 33, 34)
// + P1-BBOX-UI (docs/issues/2026-07-21-bbox-refine-crop-misleading.md).
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 16.
// P3.a: bboxHint(), nudge sub-row, refine/expand+refine/crop buttons.
// P1-BBOX-UI: Refine / Expand+Refine / Expand now queue the real
// `refine_bboxes` job (POST .../refine) instead of a plain rebox.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { BBoxSection } from "./BBoxSection";
import { bboxHint } from "./bboxUtils";
import { server } from "../../../test/server";
import type { components } from "../../../api/types";

type WordMatch = components["schemas"]["WordMatch"];
type BBox = components["schemas"]["BBox"];
type RefineScopeRequest = components["schemas"]["RefineScopeRequest"];

// ─── sonner mock ──────────────────────────────────────────────────────────
// Mocked at module level so both the direct import in lib/toast.ts and the
// dynamic import("sonner") in BBoxSection resolve to the same mock object —
// mirrors PageActionsCompact.test.tsx.
const toastMock = vi.hoisted(() => {
  const fn = Object.assign(vi.fn(), {
    loading: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
  });
  return fn;
});
vi.mock("sonner", () => ({
  toast: toastMock,
}));

/** Build a synthetic SSE frame in the real wire shape (public `Job` model +
 * `event`) — mirrors PageActionsCompact.test.tsx's `jobFrame`. */
function jobFrame(input: {
  job_id: string;
  status: string;
  progress?: { message?: string; current?: number; total?: number };
  error_message?: string | null;
}) {
  return {
    id: input.job_id,
    type: "refine_bboxes",
    project_id: "p1",
    status: input.status,
    progress: { current: 0, total: 0, message: "", ...input.progress },
    error_message: input.error_message ?? null,
    created_at: new Date(0).toISOString(),
    updated_at: new Date(0).toISOString(),
    event: input.status,
  };
}

/** Stub EventSource capturing the SSE listener so a test can dispatch a
 * synthetic job-progress event — mirrors PageActionsCompact.test.tsx. */
function mockEventSource() {
  let progressListener: ((e: MessageEvent) => void) | null = null;
  const mockES = {
    addEventListener: vi.fn((type: string, fn: unknown) => {
      if (type === "progress" || type === "complete" || type === "error") {
        progressListener = fn as (e: MessageEvent) => void;
      }
    }),
    removeEventListener: vi.fn(),
    close: vi.fn(),
    readyState: 1 as number,
  };
  vi.stubGlobal(
    "EventSource",
    vi.fn(function () {
      return mockES;
    }),
  );
  return {
    dispatch(data: Parameters<typeof jobFrame>[0]) {
      act(() => {
        progressListener?.({ data: JSON.stringify(jobFrame(data)) } as MessageEvent);
      });
    },
  };
}

const DEFAULT_BBOX: BBox = { x: 10, y: 20, width: 30, height: 15 };

function makeWord(bbox = DEFAULT_BBOX): WordMatch {
  return {
    line_index: 0,
    word_index: 0,
    ocr_text: "hello",
    ground_truth_text: "hello",
    match_status: "exact",
    normalized_match: false,
    is_validated: false,
    bbox,
  };
}

function makePageResponse(bbox: BBox) {
  return {
    project_id: "p1",
    page_index: 0,
    line_filter: "all",
    generation: 1,
    line_matches: [
      {
        line_index: 0,
        paragraph_index: 0,
        ocr_line_text: "hello",
        ground_truth_line_text: "hello",
        word_matches: [
          {
            line_index: 0,
            word_index: 0,
            ocr_text: "hello",
            ground_truth_text: "hello",
            match_status: "exact",
            normalized_match: false,
            is_validated: false,
            bbox,
          },
        ],
        overall_match_status: "exact",
        exact_count: 1,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: 1,
        is_fully_validated: false,
      },
    ],
  };
}

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderBBox(word = makeWord()) {
  const qc = makeQueryClient();
  return {
    ...render(
      <QueryClientProvider client={qc}>
        <BBoxSection word={word} projectId="p1" pageIndex={0} />
      </QueryClientProvider>,
    ),
    qc,
  };
}

// ─── bboxHint unit tests (Gap 33) ────────────────────────────────────────────

describe("bboxHint (P3.a Gap 33)", () => {
  it("formats bbox as x,y → x2,y2", () => {
    expect(bboxHint({ x: 10, y: 20, width: 30, height: 15 })).toBe("10,20 → 40,35");
  });

  it("handles zero-origin bbox", () => {
    expect(bboxHint({ x: 0, y: 0, width: 100, height: 50 })).toBe("0,0 → 100,50");
  });

  it("handles large coordinates", () => {
    expect(bboxHint({ x: 500, y: 300, width: 200, height: 80 })).toBe("500,300 → 700,380");
  });
});

// ─── BBoxSection rendering (Slice 16 original) ───────────────────────────────

describe("BBoxSection (Slice 16 + P3.a)", () => {
  beforeEach(() => {
    server.use(
      http.post("/api/projects/p1/pages/0/words/0/0/rebox", () =>
        HttpResponse.json(makePageResponse(DEFAULT_BBOX)),
      ),
      // Baseline: refine engine available. BBoxSection probes this on every
      // mount (useRefineAvailable) — tests that assert the unavailable path
      // override with their own server.use().
      http.get("/api/refine/available", () => HttpResponse.json({ available: true, reason: "" })),
    );
    vi.clearAllMocks();
  });

  it("renders four numeric inputs with initial bbox values", () => {
    renderBBox();
    const x = screen.getByTestId("bbox-input-x");
    const y = screen.getByTestId("bbox-input-y");
    const w = screen.getByTestId("bbox-input-w");
    const h = screen.getByTestId("bbox-input-h");
    expect(x.value).toBe("10");
    expect(y.value).toBe("20");
    expect(w.value).toBe("30");
    expect(h.value).toBe("15");
  });

  it("renders a Reset button", () => {
    renderBBox();
    expect(screen.getByTestId("bbox-reset-button")).toBeInTheDocument();
  });

  // ─── Review finding 1 (high): inputs must be disabled while a refine job
  // is in flight, or a keystroke made during the run is silently lost the
  // moment the completion resync fires. ──────────────────────────────────

  it("disables the coordinate inputs while a refine job is running", async () => {
    server.use(
      http.post("/api/projects/p1/pages/0/refine", () =>
        HttpResponse.json({ job_id: "job-busy-1" }, { status: 202 }),
      ),
    );
    const user = userEvent.setup();
    renderBBox();

    expect(screen.getByTestId("bbox-input-x")).not.toBeDisabled();

    await user.click(screen.getByTestId("bbox-refine-button"));

    await waitFor(() => expect(screen.getByTestId("bbox-input-x")).toBeDisabled());
    expect(screen.getByTestId("bbox-input-y")).toBeDisabled();
    expect(screen.getByTestId("bbox-input-w")).toBeDisabled();
    expect(screen.getByTestId("bbox-input-h")).toBeDisabled();
  });

  it("fires word PATCH (rebox) mutation on input blur-sm with changed value", async () => {
    const handler = vi.fn((_req: Request) =>
      Promise.resolve(HttpResponse.json(makePageResponse(DEFAULT_BBOX))),
    );
    server.use(http.post("/api/projects/p1/pages/0/words/0/0/rebox", handler));

    const user = userEvent.setup();
    renderBBox();

    const xInput = screen.getByTestId("bbox-input-x");
    await user.clear(xInput);
    await user.type(xInput, "99");
    await user.tab(); // triggers blur

    await waitFor(() => expect(handler).toHaveBeenCalledOnce());
  });

  it("Reset button shows original bbox values by resetting draft state", async () => {
    server.use(
      http.post("/api/projects/p1/pages/0/words/0/0/rebox", async ({ request }) => {
        const body = (await request.json()) as { bbox: BBox };
        return HttpResponse.json(makePageResponse(body.bbox));
      }),
    );

    const word = makeWord({ x: 5, y: 6, width: 7, height: 8 });
    const user = userEvent.setup();
    renderBBox(word);

    // Initial values should match bbox
    expect(screen.getByTestId("bbox-input-x").value).toBe("5");
    expect(screen.getByTestId("bbox-input-y").value).toBe("6");

    // Reset without any edits should fire mutation with original values
    const handler = vi.fn(async (info: { request: Request }) => {
      const body = (await info.request.json()) as { bbox: BBox };
      return HttpResponse.json(makePageResponse(body.bbox));
    });
    server.use(http.post("/api/projects/p1/pages/0/words/0/0/rebox", handler));

    await user.click(screen.getByTestId("bbox-reset-button"));

    // Mutation should have been called with the original bbox
    await waitFor(() => expect(handler).toHaveBeenCalledOnce());
  });

  it("shows outer container with data-testid=bbox-section", () => {
    renderBBox();
    expect(screen.getByTestId("bbox-section")).toBeInTheDocument();
  });

  // ─── P3.a: Nudge sub-row (Gap 34) ────────────────────────────────────────

  it("renders nudge step input and L/R/T/B direction buttons (P3.a gap 34)", () => {
    renderBBox();
    expect(screen.getByTestId("bbox-nudge-step")).toBeInTheDocument();
    expect(screen.getByTestId("bbox-nudge-left")).toBeInTheDocument();
    expect(screen.getByTestId("bbox-nudge-right")).toBeInTheDocument();
    expect(screen.getByTestId("bbox-nudge-top")).toBeInTheDocument();
    expect(screen.getByTestId("bbox-nudge-bottom")).toBeInTheDocument();
  });

  it("nudge right fires rebox mutation with x + step", async () => {
    let capturedBbox: BBox | undefined;
    server.use(
      http.post("/api/projects/p1/pages/0/words/0/0/rebox", async ({ request }) => {
        const body = (await request.json()) as { bbox: BBox };
        capturedBbox = body.bbox;
        return HttpResponse.json(makePageResponse(body.bbox));
      }),
    );

    const user = userEvent.setup();
    renderBBox(); // DEFAULT_BBOX.x = 10, step = 1

    await user.click(screen.getByTestId("bbox-nudge-right"));

    await waitFor(() => expect(capturedBbox).toBeDefined());
    expect(capturedBbox!.x).toBe(11); // 10 + 1
  });

  it("nudge top fires rebox mutation with y - step", async () => {
    let capturedBbox: BBox | undefined;
    server.use(
      http.post("/api/projects/p1/pages/0/words/0/0/rebox", async ({ request }) => {
        const body = (await request.json()) as { bbox: BBox };
        capturedBbox = body.bbox;
        return HttpResponse.json(makePageResponse(body.bbox));
      }),
    );

    const user = userEvent.setup();
    renderBBox(); // DEFAULT_BBOX.y = 20, step = 1

    await user.click(screen.getByTestId("bbox-nudge-top"));

    await waitFor(() => expect(capturedBbox).toBeDefined());
    expect(capturedBbox!.y).toBe(19); // 20 - 1
  });

  // ─── P1-BBOX-UI: Refine / Expand+Refine / Expand buttons ──────────────────
  // docs/issues/2026-07-21-bbox-refine-crop-misleading.md — these buttons
  // now queue the real refine_bboxes job (POST .../refine) instead of a
  // plain rebox. "Crop" was renamed "Expand" (testid bbox-expand-button,
  // was bbox-crop-button) since the backend has no crop capability at all.

  it("renders Refine, Expand+Refine, and Expand buttons", () => {
    renderBBox();
    expect(screen.getByTestId("bbox-refine-button")).toBeInTheDocument();
    expect(screen.getByTestId("bbox-expand-refine-button")).toBeInTheDocument();
    expect(screen.getByTestId("bbox-expand-button")).toBeInTheDocument();
    // Old testid is gone — the button no longer claims to crop.
    expect(screen.queryByTestId("bbox-crop-button")).not.toBeInTheDocument();
  });

  it("Refine posts scope=word, mode=refine, and this word's indices to /refine", async () => {
    let capturedBody: RefineScopeRequest | undefined;
    server.use(
      http.post("/api/projects/p1/pages/0/refine", async ({ request }) => {
        capturedBody = (await request.json()) as RefineScopeRequest;
        return HttpResponse.json({ job_id: "job-refine-1" }, { status: 202 });
      }),
    );

    const user = userEvent.setup();
    renderBBox(makeWord(DEFAULT_BBOX)); // line_index 0, word_index 0

    await user.click(screen.getByTestId("bbox-refine-button"));

    await waitFor(() => expect(capturedBody).toBeDefined());
    expect(capturedBody!.scope).toBe("word");
    expect(capturedBody!.mode).toBe("refine");
    expect(capturedBody!.word_indices).toEqual([[0, 0]]);
  });

  it("Expand+Refine posts mode=expand_then_refine with this word's indices", async () => {
    let capturedBody: RefineScopeRequest | undefined;
    server.use(
      http.post("/api/projects/p1/pages/0/refine", async ({ request }) => {
        capturedBody = (await request.json()) as RefineScopeRequest;
        return HttpResponse.json({ job_id: "job-expand-refine-1" }, { status: 202 });
      }),
    );

    const user = userEvent.setup();
    renderBBox();

    await user.click(screen.getByTestId("bbox-expand-refine-button"));

    await waitFor(() => expect(capturedBody).toBeDefined());
    expect(capturedBody!.scope).toBe("word");
    expect(capturedBody!.mode).toBe("expand_then_refine");
    expect(capturedBody!.word_indices).toEqual([[0, 0]]);
  });

  it("Expand posts mode=expand_only with this word's indices", async () => {
    let capturedBody: RefineScopeRequest | undefined;
    server.use(
      http.post("/api/projects/p1/pages/0/refine", async ({ request }) => {
        capturedBody = (await request.json()) as RefineScopeRequest;
        return HttpResponse.json({ job_id: "job-expand-1" }, { status: 202 });
      }),
    );

    const user = userEvent.setup();
    renderBBox();

    await user.click(screen.getByTestId("bbox-expand-button"));

    await waitFor(() => expect(capturedBody).toBeDefined());
    expect(capturedBody!.scope).toBe("word");
    expect(capturedBody!.mode).toBe("expand_only");
    expect(capturedBody!.word_indices).toEqual([[0, 0]]);
  });

  it("posts the clicked word's own (line, word) indices, not (0, 0)", async () => {
    let capturedBody: RefineScopeRequest | undefined;
    server.use(
      http.post("/api/projects/p1/pages/0/refine", async ({ request }) => {
        capturedBody = (await request.json()) as RefineScopeRequest;
        return HttpResponse.json({ job_id: "job-indices-1" }, { status: 202 });
      }),
    );

    const word: WordMatch = { ...makeWord(DEFAULT_BBOX), line_index: 3, word_index: 5 };
    const user = userEvent.setup();
    renderBBox(word);

    await user.click(screen.getByTestId("bbox-refine-button"));

    await waitFor(() => expect(capturedBody).toBeDefined());
    expect(capturedBody!.word_indices).toEqual([[3, 5]]);
  });

  it("a completed refine job invalidates the page query", async () => {
    server.use(
      http.post("/api/projects/p1/pages/0/refine", () =>
        HttpResponse.json({ job_id: "job-complete-1" }, { status: 202 }),
      ),
    );
    const qc = makeQueryClient();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const es = mockEventSource();
    const user = userEvent.setup();

    render(
      <QueryClientProvider client={qc}>
        <BBoxSection word={makeWord()} projectId="p1" pageIndex={0} />
      </QueryClientProvider>,
    );

    await user.click(screen.getByTestId("bbox-refine-button"));
    await waitFor(() => expect(toastMock.loading).toHaveBeenCalled());

    es.dispatch({ job_id: "job-complete-1", status: "complete" });

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ["page", "p1", 0] }),
      ),
    );

    vi.unstubAllGlobals();
  });

  it("a completed refine job's invalidated refetch updates the coordinate inputs", async () => {
    // Regression guard: BBoxSection's `draft` used to be a mount-time-only
    // snapshot of `word.bbox` — invalidating the page query refetched fresh
    // data, but nothing resynced `draft` to it, so the coordinate inputs
    // stayed on the pre-refine values even though the server (and the rest
    // of the app, reading the same refetched query) had already moved on.
    // This wraps BBoxSection in a small harness that subscribes to the same
    // `["page", projectId, pageIndex]` query WordDetail does, passing the
    // refetched word down as a fresh prop — the render-time resync in
    // BBoxSection should pick it up once the job completes.
    // The GET handler mimics a real backend: it keeps returning the
    // original bbox until the refine POST has actually landed, only then
    // switching to the expanded one — a handler hardcoded to the expanded
    // value from the start would mask this test's whole premise, since
    // TanStack Query's default `refetchOnMount` would pick it up on mount,
    // long before the job ever "completes".
    const EXPANDED_BBOX: BBox = { x: 6, y: 16, width: 38, height: 23 };
    let currentBbox = DEFAULT_BBOX;
    server.use(
      http.post("/api/projects/p1/pages/0/refine", () => {
        currentBbox = EXPANDED_BBOX;
        return HttpResponse.json({ job_id: "job-sync-1" }, { status: 202 });
      }),
      http.get("/api/projects/p1/pages/0", () => HttpResponse.json(makePageResponse(currentBbox))),
    );

    function Harness() {
      const q = useQuery({
        queryKey: ["page", "p1", 0],
        queryFn: async () => {
          const res = await fetch("/api/projects/p1/pages/0");
          return res.json() as Promise<ReturnType<typeof makePageResponse>>;
        },
        initialData: makePageResponse(DEFAULT_BBOX),
      });
      const word = q.data.line_matches[0].word_matches[0];
      return <BBoxSection word={word} projectId="p1" pageIndex={0} />;
    }

    const qc = makeQueryClient();
    const es = mockEventSource();
    const user = userEvent.setup();

    render(
      <QueryClientProvider client={qc}>
        <Harness />
      </QueryClientProvider>,
    );

    expect(screen.getByTestId("bbox-input-x").value).toBe("10");

    await user.click(screen.getByTestId("bbox-expand-refine-button"));
    await waitFor(() => expect(toastMock.loading).toHaveBeenCalled());

    es.dispatch({ job_id: "job-sync-1", status: "complete" });

    await waitFor(() => {
      expect(screen.getByTestId("bbox-input-x").value).toBe("6");
    });
    expect(screen.getByTestId("bbox-input-y").value).toBe("16");
    expect(screen.getByTestId("bbox-input-w").value).toBe("38");
    expect(screen.getByTestId("bbox-input-h").value).toBe("23");

    vi.unstubAllGlobals();
  });

  it("a failed refine job shows an error toast", async () => {
    server.use(
      http.post("/api/projects/p1/pages/0/refine", () =>
        HttpResponse.json({ job_id: "job-fail-1" }, { status: 202 }),
      ),
    );
    const es = mockEventSource();
    const user = userEvent.setup();
    renderBBox();

    await user.click(screen.getByTestId("bbox-refine-button"));
    await waitFor(() => expect(toastMock.loading).toHaveBeenCalled());

    es.dispatch({
      job_id: "job-fail-1",
      status: "error",
      error_message: "refine_bboxes: page 0 not loaded; run OCR / load first",
    });

    await waitFor(() => {
      const calls = toastMock.mock.calls as [unknown, { style?: { borderLeft?: string } }?][];
      const errorCall = calls.find(
        ([msg, opts]) =>
          msg === "refine_bboxes: page 0 not loaded; run OCR / load first" &&
          opts?.style?.borderLeft?.includes("status-mismatch"),
      );
      expect(errorCall).toBeDefined();
    });

    vi.unstubAllGlobals();
  });

  it("a POST failure to start the refine job shows an error toast", async () => {
    server.use(
      http.post("/api/projects/p1/pages/0/refine", () =>
        HttpResponse.text("boom", { status: 500 }),
      ),
    );
    const user = userEvent.setup();
    renderBBox();

    await user.click(screen.getByTestId("bbox-refine-button"));

    await waitFor(() => {
      const calls = toastMock.mock.calls as [unknown, { style?: { borderLeft?: string } }?][];
      const errorCall = calls.find(([, opts]) =>
        opts?.style?.borderLeft?.includes("status-mismatch"),
      );
      expect(errorCall).toBeDefined();
    });
  });

  // ─── P1-BBOX-UI: useRefineAvailable capability gate ────────────────────────

  it("disables Refine/Expand+Refine/Expand and explains why when the probe reports unavailable", async () => {
    server.use(
      http.get("/api/refine/available", () =>
        HttpResponse.json({ available: false, reason: "no OCR engine wired" }),
      ),
    );

    renderBBox();

    await waitFor(() => expect(screen.getByTestId("bbox-refine-button")).toBeDisabled());
    expect(screen.getByTestId("bbox-expand-refine-button")).toBeDisabled();
    expect(screen.getByTestId("bbox-expand-button")).toBeDisabled();
    expect(screen.getByTestId("bbox-refine-unavailable")).toBeInTheDocument();
  });

  it("clicking a disabled Refine button while unavailable never posts to /refine", async () => {
    server.use(
      http.get("/api/refine/available", () =>
        HttpResponse.json({ available: false, reason: "no OCR engine wired" }),
      ),
    );
    const spy = vi.fn(() => HttpResponse.json({ job_id: "should-not-fire" }, { status: 202 }));
    server.use(http.post("/api/projects/p1/pages/0/refine", spy));

    const user = userEvent.setup();
    renderBBox();

    await waitFor(() => expect(screen.getByTestId("bbox-refine-button")).toBeDisabled());
    await user.click(screen.getByTestId("bbox-refine-button"));

    expect(spy).not.toHaveBeenCalled();
  });

  it("still allows manual rebox (nudge) while refine is unavailable", async () => {
    server.use(
      http.get("/api/refine/available", () =>
        HttpResponse.json({ available: false, reason: "no OCR engine wired" }),
      ),
    );

    const user = userEvent.setup();
    renderBBox();

    await waitFor(() => expect(screen.getByTestId("bbox-refine-button")).toBeDisabled());
    expect(screen.getByTestId("bbox-nudge-right")).not.toBeDisabled();
  });
});
