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

  // POST .../words/{li}/{wi}/char-ranges — fire-and-forget word mutation that
  // can resolve AFTER its test's afterEach resetHandlers() ran (hotkey-driven
  // in ProjectPage tests). A per-test server.use() handler is already gone by
  // then, so only a DEFAULT handler prevents the timing-dependent
  // "unhandled request" rejection that intermittently fails the whole suite.
  http.post("/api/projects/:pid/pages/:idx/words/:li/:wi/char-ranges", () => HttpResponse.json({})),
];
