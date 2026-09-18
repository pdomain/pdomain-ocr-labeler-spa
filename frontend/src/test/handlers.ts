// Default msw handlers shared across the test suite.
//
// Baseline handlers below keep common endpoints from emitting "unhandled
// request" errors (onUnhandledRequest: "error" in setup.ts).  Per-test
// overrides are registered via server.use(...) and reset by afterEach.
import { http, HttpResponse } from "msw";
import type { RequestHandler } from "msw";

export const handlers: RequestHandler[] = [
  // GET /api/fs/ls — directory-listing helper used by SourceFolderDialog on
  // every mount.  Default returns an empty directory so existing tests that
  // don't care about the listing don't receive MSW "unhandled request" errors.
  http.get("/api/fs/ls", () => HttpResponse.json({ path: "/", entries: [] })),

  // GET /api/projects — project list. Default returns no source root and no
  // projects; SourceFolderDialog fetches this on open to pre-populate its path.
  http.get("/api/projects", () =>
    HttpResponse.json({
      projects: [],
      projects_root: "",
      selected: null,
      config_source: "default",
    }),
  ),

  // GET /api/label-vocabulary — Q-B2-STYLE-LABELS option (b).
  // Default returns the canonical book-tools vocabulary so tests that render
  // ToolbarActionGrid / StylePalette / ComponentPalette do not receive MSW
  // "unhandled request" errors. Per-test overrides use server.use().
  http.get("/api/label-vocabulary", () =>
    HttpResponse.json({
      text_style_labels: [
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
      ],
      word_components: [
        "drop cap",
        "drop cap unrecovered",
        "footnote marker",
        "subscript",
        "superscript",
      ],
    }),
  ),

  // POST /api/projects/:projectId/current-page-index — page-cursor persistence
  // (GAP-3).  ProjectPage fires this 300 ms after mount via a debounced,
  // fire-and-forget `void fetch(...)` with no rejection handler
  // (ProjectPage.tsx).  Any test that keeps ProjectPage mounted past the
  // debounce window triggers the POST; without a baseline handler it hits
  // onUnhandledRequest: "error" and surfaces as an unhandled rejection that
  // fails the whole vitest run even when every test passes.  Tests that assert
  // the cursor POST override this with server.use().
  http.post("/api/projects/:projectId/current-page-index", () => HttpResponse.json({})),

  // GET /api/suite/installed — default: no apps installed (trainer absent).
  // Tests that need the trainer button visible override with server.use().
  http.get("/api/suite/installed", () => HttpResponse.json([])),

  // POST /api/suite/launch — default stub for the Send-to-trainer button.
  http.post("/api/suite/launch", () =>
    HttpResponse.json({ kind: "opened", url: "http://localhost:8090", spawned: true, pid: 0 }),
  ),

  http.get("/api/projects/:pid/pages/:idx/typography/review", () =>
    HttpResponse.json({
      project_id: "",
      page_index: 0,
      logical_page_id: "",
      reviewed_words: 0,
      text_reviewed_words: 0,
      typography_reviewed_words: 0,
      blocked_words: 0,
      total_words: 0,
      complete: true,
      heads: [],
    }),
  ),

  // Region review surface (docs/plans/2026-09-17-region-review-surface.md,
  // Task 3) — baseline handlers for the six region routes so tests that mount
  // components using useRegionMutations / useProposalRuns without overriding
  // a specific route don't hit onUnhandledRequest: "error". Tests that assert
  // method/path/body register their own server.use(...) override.
  http.post("/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/accept", () =>
    HttpResponse.json({ project_id: "", page_index: 0, line_matches: [] }),
  ),
  http.post("/api/projects/:pid/pages/:idx/regions/proposals/:proposalId/reject", () =>
    HttpResponse.json({ project_id: "", page_index: 0, line_matches: [] }),
  ),
  http.patch("/api/projects/:pid/pages/:idx/regions/:regionId", () =>
    HttpResponse.json({ project_id: "", page_index: 0, line_matches: [] }),
  ),
  http.delete("/api/projects/:pid/pages/:idx/regions/:regionId", () =>
    HttpResponse.json({ project_id: "", page_index: 0, line_matches: [] }),
  ),
  http.post("/api/projects/:pid/propose-page-kinds", () =>
    HttpResponse.json({ job_id: "job-1" }, { status: 202 }),
  ),
  http.post("/api/projects/:pid/regions/propose", () =>
    HttpResponse.json({ job_id: "job-1" }, { status: 202 }),
  ),

  // Book review queue (docs/specs/2026-09-17-book-review-queue-design.md) —
  // baseline handler so any component/hook mounting useReviewQueue (Rail's
  // badge, useRegionReviewHotkeys' bracket keys) without an explicit
  // override doesn't hit onUnhandledRequest: "error". Default: an empty
  // queue. Tests that assert queue-driven behavior register their own
  // server.use(...) override.
  http.get("/api/projects/:pid/regions/review-queue", () =>
    HttpResponse.json({ total_undecided: 0, pages: [], items: [] }),
  ),

  // One-answer-to-what-to-review-next (pdomain-ocr-synth's
  // docs/specs/2026-09-18-one-answer-to-what-to-review-next.md) — baseline
  // handler for the per-kind book review queue, so any component/hook
  // mounting useBookReviewQueue (Rail's "next kind" badge, the Queue drawer
  // tab's kind selector, useRegionReviewHotkeys' bracket keys) without an
  // explicit override doesn't hit onUnhandledRequest: "error". Default: every
  // kind reports zero outstanding work, so nothing is actionable and
  // `firstActionableKind` resolves to `undefined` — this keeps every
  // pre-existing region-only test's fallback-to-"region" behavior intact.
  // Tests that assert kind-driven behavior register their own
  // server.use(...) override.
  http.get("/api/projects/:pid/review-queue", () =>
    HttpResponse.json({
      kinds: [
        {
          kind: "page_kind",
          outstanding: 0,
          total: 0,
          available: true,
          blocked_by: null,
          first_page_index: null,
          pages_not_counted: 0,
          is_lower_bound: false,
        },
        {
          kind: "region",
          outstanding: 0,
          total: 0,
          available: true,
          blocked_by: null,
          first_page_index: null,
          pages_not_counted: 0,
          is_lower_bound: false,
        },
        {
          kind: "word",
          outstanding: 0,
          total: 0,
          available: true,
          blocked_by: null,
          first_page_index: null,
          pages_not_counted: 0,
          is_lower_bound: false,
        },
        {
          kind: "typography",
          outstanding: 0,
          total: 0,
          available: true,
          blocked_by: null,
          first_page_index: null,
          pages_not_counted: 0,
          is_lower_bound: false,
        },
        {
          kind: "glyph",
          outstanding: 0,
          total: 0,
          available: false,
          blocked_by: null,
          first_page_index: null,
          pages_not_counted: 0,
          is_lower_bound: false,
          unavailable_reason: "no glyph predictor is wired",
        },
      ],
    }),
  ),

  // Page-kind review (pdomain-ocr-synth's
  // docs/specs/2026-09-17-page-kind-review-design.md) — baseline handlers for
  // the book-wide list, the bulk confirm route, and the single-page confirm
  // route, so components/hooks that mount without an explicit override don't
  // hit onUnhandledRequest: "error". Tests that assert route behavior
  // register their own server.use(...) override.
  http.get("/api/projects/:pid/page-kinds", () =>
    HttpResponse.json({ total_pages: 0, reviewed_count: 0, pages: [] }),
  ),
  http.post("/api/projects/:pid/page-kinds/confirm", () =>
    HttpResponse.json({ results: [], confirmed_count: 0 }),
  ),
  http.post("/api/projects/:pid/pages/:idx/page-kind", () =>
    HttpResponse.json({ project_id: "", page_index: 0, page_kind_reviewed: false }),
  ),
];
