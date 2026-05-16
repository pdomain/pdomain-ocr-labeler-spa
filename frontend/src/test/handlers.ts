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
];
