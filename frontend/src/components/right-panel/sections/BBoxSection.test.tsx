// BBoxSection.test.tsx — Tests for Slice 16 bounding-box editor + P3.a (Gaps 33, 34)
// + P1-BBOX-UI (docs/issues/2026-07-21-bbox-refine-crop-misleading.md).
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 16.
// P3.a: bboxHint(), nudge sub-row, refine/expand+refine/crop buttons.
// P1-BBOX-UI: Refine / Expand+Refine / Expand now queue the real
// `refine_bboxes` job (POST .../refine) instead of a plain rebox.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { useSyncExternalStore } from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { BBoxSection } from "./BBoxSection";
import { bboxHint } from "./bboxUtils";
import { server } from "../../../test/server";
import type {
  BboxRefineOutcome,
  UseBboxRefineTrackingResult,
} from "../../../hooks/useBboxRefineTracking";
import type { components } from "../../../api/types";

type WordMatch = components["schemas"]["WordMatch"];
type BBox = components["schemas"]["BBox"];
type RefineScopeRequest = components["schemas"]["RefineScopeRequest"];

// ─── sonner mock ──────────────────────────────────────────────────────────
// Mocked at module level so both the direct import in lib/toast.ts and the
// dynamic import("sonner") in BBoxSection resolve to the same mock object —
// mirrors PageActionsCompact.test.tsx. Review finding 3 moved the
// completion toast lifecycle to useBboxRefineTracking (its own test file
// covers that); what stays local to BBoxSection is the immediate "job
// started" loading toast and the POST-failure error toast, both still
// exercised below.
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

// ─── fake refineTracking (review finding 3) ────────────────────────────────
// Review finding 3 hoisted the refine_bboxes job tracker out of BBoxSection
// into useBboxRefineTracking, owned by an always-mounted ancestor
// (ProjectPage) and threaded down as a prop. This fake stands in for that
// ancestor in tests: a plain external store (same shape as this app's
// worklistStore/dialogStore) a test can drive directly (`start` /
// `completeWith` / `clearJob`), read reactively through
// `useSyncExternalStore` inside a small wrapper component — real SSE-level
// behavior (EventSource wiring, invalidation, toast wording) is covered by
// useBboxRefineTracking.test.tsx; this file only needs to prove BBoxSection
// consumes the resulting `{ jobId, word, outcome, start }` shape correctly.
// `start`/`completeWith` qualify by ("p1", 0) — every test below renders
// BBoxSection with that same projectId/pageIndex, matching what the real
// hook's `start()` would have captured (review round 2 finding 1).
interface FakeRefineTrackingState {
  jobId: string | null;
  word: UseBboxRefineTrackingResult["word"];
  outcome: BboxRefineOutcome | null;
}

function createFakeRefineTracking() {
  let state: FakeRefineTrackingState = { jobId: null, word: null, outcome: null };
  const listeners = new Set<() => void>();
  function notify() {
    listeners.forEach((l) => {
      l();
    });
  }
  function subscribe(cb: () => void) {
    listeners.add(cb);
    return () => {
      listeners.delete(cb);
    };
  }
  function getSnapshot() {
    return state;
  }
  function start(jobId: string, wordKey: string) {
    state = { ...state, jobId, word: { projectId: "p1", pageIndex: 0, wordKey } };
    notify();
  }
  /** Simulate the ancestor's real hook delivering a terminal outcome —
   * clears the in-flight job and (for a real refine) records the outcome
   * this word's BBoxSection should react to. */
  function completeWith(wordKey: string, refined: number) {
    state = {
      jobId: null,
      word: null,
      outcome: {
        word: { projectId: "p1", pageIndex: 0, wordKey },
        refined,
        token: (state.outcome?.token ?? 0) + 1,
      },
    };
    notify();
  }
  function useTracking(): UseBboxRefineTrackingResult {
    const snapshot = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
    return { jobId: snapshot.jobId, word: snapshot.word, outcome: snapshot.outcome, start };
  }
  return { useTracking, start, completeWith, getState: getSnapshot };
}

type FakeRefineTracking = ReturnType<typeof createFakeRefineTracking>;

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

function renderBBox(word = makeWord(), tracking: FakeRefineTracking = createFakeRefineTracking()) {
  const qc = makeQueryClient();
  function Wrapper() {
    const refineTracking = tracking.useTracking();
    return <BBoxSection word={word} projectId="p1" pageIndex={0} refineTracking={refineTracking} />;
  }
  return {
    ...render(
      <QueryClientProvider client={qc}>
        <Wrapper />
      </QueryClientProvider>,
    ),
    qc,
    tracking,
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

  // ─── Review round 2, findings 2/3 (superseding round 1 finding 1): the
  // coordinate inputs are never disabled by refine-job state — see the
  // module doc comment for why a disable-based fix kept reopening this
  // same window. Nudge/Reset (one-shot clicks, not typing sessions) still
  // gate on the job instead, to protect the tracker's one job slot. ──────

  it("never disables the coordinate inputs while a refine job is running", async () => {
    server.use(
      http.post("/api/projects/p1/pages/0/refine", () =>
        HttpResponse.json({ job_id: "job-busy-1" }, { status: 202 }),
      ),
    );
    const user = userEvent.setup();
    renderBBox();

    expect(screen.getByTestId("bbox-input-x")).not.toBeDisabled();

    await user.click(screen.getByTestId("bbox-refine-button"));

    // The job is now running for this word (Nudge/Reset gate on it)…
    await waitFor(() => expect(screen.getByTestId("bbox-nudge-right")).toBeDisabled());
    expect(screen.getByTestId("bbox-reset-button")).toBeDisabled();
    // …but the coordinate inputs stay usable throughout.
    expect(screen.getByTestId("bbox-input-x")).not.toBeDisabled();
    expect(screen.getByTestId("bbox-input-y")).not.toBeDisabled();
    expect(screen.getByTestId("bbox-input-w")).not.toBeDisabled();
    expect(screen.getByTestId("bbox-input-h")).not.toBeDisabled();
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

  it("Refine calls refineTracking.start with the returned job id and this word's key", async () => {
    server.use(
      http.post("/api/projects/p1/pages/0/refine", () =>
        HttpResponse.json({ job_id: "job-start-1" }, { status: 202 }),
      ),
    );
    const user = userEvent.setup();
    const { tracking } = renderBBox(makeWord(DEFAULT_BBOX)); // line_index 0, word_index 0

    await user.click(screen.getByTestId("bbox-refine-button"));

    await waitFor(() => expect(tracking.getState().jobId).toBe("job-start-1"));
    expect(tracking.getState().word).toEqual({ projectId: "p1", pageIndex: 0, wordKey: "0-0" });
  });

  it("a delivered outcome for this word's key resyncs the coordinate inputs", async () => {
    // Regression guard (review finding 3 follow-on of the original P1-BBOX-UI
    // fix): BBoxSection's `draft` used to be a mount-time-only snapshot of
    // `word.bbox`. The completion outcome now arrives as a prop
    // (`refineTracking.outcome`) instead of a locally-owned SSE stream —
    // this proves BBoxSection still resyncs `draft` once a matching,
    // real (`refined > 0`) outcome for this word lands, the same way it did
    // before the job tracker moved out to useBboxRefineTracking.
    // The GET handler mimics a real backend: it keeps returning the
    // original bbox until the caller "commits" the expanded one — a
    // handler hardcoded to the expanded value from the start would mask
    // this test's premise, since TanStack Query's default `refetchOnMount`
    // would pick it up on mount, long before any outcome arrives.
    const EXPANDED_BBOX: BBox = { x: 6, y: 16, width: 38, height: 23 };
    let currentBbox = DEFAULT_BBOX;
    server.use(
      http.get("/api/projects/p1/pages/0", () => HttpResponse.json(makePageResponse(currentBbox))),
    );

    const tracking = createFakeRefineTracking();
    const qc = makeQueryClient();

    function Harness() {
      const q = useQuery({
        queryKey: ["page", "p1", 0],
        queryFn: async () => {
          const res = await fetch("/api/projects/p1/pages/0");
          return res.json() as Promise<ReturnType<typeof makePageResponse>>;
        },
        initialData: makePageResponse(DEFAULT_BBOX),
      });
      const refineTracking = tracking.useTracking();
      const word = q.data.line_matches[0].word_matches[0];
      return (
        <BBoxSection word={word} projectId="p1" pageIndex={0} refineTracking={refineTracking} />
      );
    }

    render(
      <QueryClientProvider client={qc}>
        <Harness />
      </QueryClientProvider>,
    );

    expect(screen.getByTestId("bbox-input-x").value).toBe("10");

    // Real timing (see useBboxRefineTracking.ts's onComplete): the outcome
    // is recorded and the page query is invalidated in the same tick, and
    // the invalidation's refetch resolves afterward — arming
    // `pendingRefineSync` before `word.bbox` actually changes is exactly
    // what lets BBoxSection tell "this bbox change is the refine's result"
    // apart from an unrelated one (review finding 2). Reproduce that
    // ordering here: outcome first, then the bbox catches up.
    act(() => {
      tracking.completeWith("0-0", 1);
    });
    currentBbox = EXPANDED_BBOX;
    await act(async () => {
      await qc.invalidateQueries({ queryKey: ["page", "p1", 0] });
    });

    await waitFor(() => {
      expect(screen.getByTestId("bbox-input-x").value).toBe("6");
    });
    expect(screen.getByTestId("bbox-input-y").value).toBe("16");
    expect(screen.getByTestId("bbox-input-w").value).toBe("38");
    expect(screen.getByTestId("bbox-input-h").value).toBe("23");
  });

  // ─── Review round 2, finding 2 (medium — reopens finding 1's window):
  // the coordinate inputs must never be disabled (the earlier "disable
  // while busy" approach only ever narrows this window, it doesn't close
  // it — see BBoxSection.tsx's module doc comment for the reasoning behind
  // this direction change). A resync instead leaves whichever field
  // currently has focus untouched, merging its result into the rest. ────

  it("keeps typing into a focused field while this word's own refine job runs and its result arrives", async () => {
    const EXPANDED_BBOX: BBox = { x: 6, y: 16, width: 38, height: 23 };
    let currentBbox = DEFAULT_BBOX;
    server.use(
      http.get("/api/projects/p1/pages/0", () => HttpResponse.json(makePageResponse(currentBbox))),
    );

    const tracking = createFakeRefineTracking();
    const qc = makeQueryClient();

    function Harness() {
      const q = useQuery({
        queryKey: ["page", "p1", 0],
        queryFn: async () => {
          const res = await fetch("/api/projects/p1/pages/0");
          return res.json() as Promise<ReturnType<typeof makePageResponse>>;
        },
        initialData: makePageResponse(DEFAULT_BBOX),
      });
      const refineTracking = tracking.useTracking();
      const word = q.data.line_matches[0].word_matches[0];
      return (
        <BBoxSection word={word} projectId="p1" pageIndex={0} refineTracking={refineTracking} />
      );
    }

    const user = userEvent.setup();
    render(
      <QueryClientProvider client={qc}>
        <Harness />
      </QueryClientProvider>,
    );

    // A refine job for this word is already running (e.g. the user just
    // clicked Refine) — the inputs must stay usable regardless.
    act(() => {
      tracking.start("job-typing-1", "0-0");
    });

    const xInput = screen.getByTestId("bbox-input-x");
    expect(xInput).not.toBeDisabled();
    await user.click(xInput);
    await user.clear(xInput);
    await user.type(xInput, "777"); // uncommitted — no blur yet

    // The job's result arrives while X is still focused, mid-edit.
    act(() => {
      tracking.completeWith("0-0", 1);
    });
    currentBbox = EXPANDED_BBOX;
    await act(async () => {
      await qc.invalidateQueries({ queryKey: ["page", "p1", 0] });
    });

    // Y/W/H — not focused — pick up the refine's result immediately.
    await waitFor(() => {
      expect(screen.getByTestId("bbox-input-y").value).toBe("16");
    });
    expect(screen.getByTestId("bbox-input-w").value).toBe("38");
    expect(screen.getByTestId("bbox-input-h").value).toBe("23");
    // X — still focused — keeps exactly what the user is typing.
    expect(screen.getByTestId("bbox-input-x").value).toBe("777");
  });

  // ─── Review finding 2 (high): refine and expand_then_refine no-op when
  // the page has no cv2_numpy_page_image (true for any page loaded from the
  // store) — a documented outcome, not an edge case. The resync must key
  // off the outcome's `refined` count. See useBboxRefineTracking.test.tsx
  // for the toast-wording coverage (that lives in the hook now). ─────────

  it("a no-op outcome (refined: 0) does not arm a resync for a later, unrelated bbox change", async () => {
    // The bug this guards: `pendingRefineSync` used to arm unconditionally
    // on any "complete" status. A no-op refine never changes `word.bbox`,
    // so the flag just sat there armed — until some later, wholly
    // unrelated change to `word.bbox` (a GT rematch, a different word's
    // edit landing on the same query, anything) arrived as a fresh prop
    // and got silently snapped into `draft`, as if IT were the refine's
    // result.
    let currentBbox: BBox = DEFAULT_BBOX;
    server.use(
      http.get("/api/projects/p1/pages/0", () => HttpResponse.json(makePageResponse(currentBbox))),
    );

    const tracking = createFakeRefineTracking();
    const qc = makeQueryClient();

    function Harness() {
      const q = useQuery({
        queryKey: ["page", "p1", 0],
        queryFn: async () => {
          const res = await fetch("/api/projects/p1/pages/0");
          return res.json() as Promise<ReturnType<typeof makePageResponse>>;
        },
        initialData: makePageResponse(DEFAULT_BBOX),
      });
      const refineTracking = tracking.useTracking();
      const word = q.data.line_matches[0].word_matches[0];
      return (
        <BBoxSection word={word} projectId="p1" pageIndex={0} refineTracking={refineTracking} />
      );
    }

    render(
      <QueryClientProvider client={qc}>
        <Harness />
      </QueryClientProvider>,
    );

    // The job completes as a genuine no-op — nothing was refined.
    act(() => {
      tracking.completeWith("0-0", 0);
    });

    // Now something else entirely changes this word's bbox and the same
    // page query is invalidated — nothing to do with the no-op refine
    // above. If the flag were still armed, this arrival would get
    // misattributed to "the refine finished" and silently overwrite draft.
    currentBbox = { x: 999, y: 999, width: 999, height: 999 };
    await act(async () => {
      await qc.invalidateQueries({ queryKey: ["page", "p1", 0] });
    });
    await waitFor(() => expect(qc.getQueryData(["page", "p1", 0])).toBeDefined());

    expect(screen.getByTestId("bbox-input-x").value).toBe("10");
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

  // ─── Review finding 4 (medium): refineTracking.jobId is one shared value
  // across every word; a job started on one word must not disable another
  // word's controls with no explanation. ─────────────────────────────────

  it("does not disable this word's controls while a DIFFERENT word's refine job runs", async () => {
    const tracking = createFakeRefineTracking();
    act(() => {
      tracking.start("job-other-word", "9-9");
    });

    renderBBox(makeWord(DEFAULT_BBOX), tracking); // this word is "0-0"

    expect(screen.getByTestId("bbox-input-x")).not.toBeDisabled();
    expect(screen.getByTestId("bbox-nudge-right")).not.toBeDisabled();
    expect(screen.getByTestId("bbox-reset-button")).not.toBeDisabled();
  });

  it("disables this word's refine buttons (not its manual controls) while a different word's job runs, and says why", async () => {
    const tracking = createFakeRefineTracking();
    act(() => {
      tracking.start("job-other-word", "9-9");
    });

    renderBBox(makeWord(DEFAULT_BBOX), tracking); // this word is "0-0"

    const refineButton = screen.getByTestId("bbox-refine-button");
    // The availability probe (msw) resolves asynchronously; wait past its
    // loading state so the title reflects the "other word" reason, not
    // "checking availability".
    await waitFor(() => expect(refineButton.title.toLowerCase()).toContain("another word"));
    expect(refineButton).toBeDisabled();
    expect(screen.getByTestId("bbox-expand-refine-button")).toBeDisabled();
    expect(screen.getByTestId("bbox-expand-button")).toBeDisabled();

    // Manual editing stays available — only the job-backed buttons wait.
    expect(screen.getByTestId("bbox-input-x")).not.toBeDisabled();
  });

  it("still disables Nudge/Reset (not the inputs) while this word's own refine job runs", async () => {
    server.use(
      http.post("/api/projects/p1/pages/0/refine", () =>
        HttpResponse.json({ job_id: "job-this-word" }, { status: 202 }),
      ),
    );
    const user = userEvent.setup();
    renderBBox(makeWord(DEFAULT_BBOX)); // "0-0"

    await user.click(screen.getByTestId("bbox-refine-button"));

    await waitFor(() => expect(screen.getByTestId("bbox-nudge-right")).toBeDisabled());
    expect(screen.getByTestId("bbox-reset-button")).toBeDisabled();
    // Round 2 findings 2/3: the coordinate inputs are never disabled.
    expect(screen.getByTestId("bbox-input-x")).not.toBeDisabled();
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
