// jobsMapping.test.ts — unit tests for the backend Job → pdomain-ui JobRow /
// JobsPill mapping.
//
// Spec: docs/plans/2026-07-21-pgdp-alignment-remaining.md item 4.
// Verifies the mapping this repo's own gap report
// (docs/issues/2026-09-18-jobs-pill-status-contract-gap.md) blocked on:
// `cancelled` maps to its own honest status (not `failed`, `done`, or
// `paused`), and every row is `pausable: false` (this backend has no
// pause/resume concept).

import { describe, it, expect } from "vitest";
import { toJobRowJob, toJobRowJobs, toPillActiveJobs } from "./jobsMapping";
import type { JobsListJob } from "../hooks/useJobsList";

function makeJob(overrides: Partial<JobsListJob>): JobsListJob {
  return {
    id: "job-1",
    type: "export",
    project_id: "proj-1",
    status: "running",
    progress: { current: 1, total: 4, message: "Exporting page 1 of 4" },
    error_message: null,
    created_at: "2026-09-18T00:00:00Z",
    updated_at: "2026-09-18T00:00:00Z",
    result: null,
    ...overrides,
  };
}

describe("toJobRowJob", () => {
  it("maps cancelled to its own honest status, not failed/done/paused", () => {
    const row = toJobRowJob(makeJob({ status: "cancelled" }));
    expect(row.status).toBe("cancelled");
  });

  it("maps error to failed", () => {
    const row = toJobRowJob(makeJob({ status: "error", error_message: "disk full" }));
    expect(row.status).toBe("failed");
  });

  it("maps complete to done with 100% progress regardless of the raw counters", () => {
    const row = toJobRowJob(
      makeJob({ status: "complete", progress: { current: 3, total: 4, message: "" } }),
    );
    expect(row.status).toBe("done");
    expect(row.pct).toBe(100);
  });

  it("maps queued and running through unchanged", () => {
    expect(toJobRowJob(makeJob({ status: "queued" })).status).toBe("queued");
    expect(toJobRowJob(makeJob({ status: "running" })).status).toBe("running");
  });

  it("is always pausable: false — this backend has no pause/resume concept", () => {
    for (const status of ["queued", "running", "complete", "error", "cancelled"] as const) {
      expect(toJobRowJob(makeJob({ status })).pausable).toBe(false);
    }
  });

  it("is cancelable only while queued or running", () => {
    expect(toJobRowJob(makeJob({ status: "queued" })).cancelable).toBe(true);
    expect(toJobRowJob(makeJob({ status: "running" })).cancelable).toBe(true);
    expect(toJobRowJob(makeJob({ status: "complete" })).cancelable).toBe(false);
    expect(toJobRowJob(makeJob({ status: "error" })).cancelable).toBe(false);
    expect(toJobRowJob(makeJob({ status: "cancelled" })).cancelable).toBe(false);
  });

  it("prefers the backend error message for a failed job's phase line", () => {
    const row = toJobRowJob(
      makeJob({
        status: "error",
        error_message: "disk full",
        progress: { current: 1, total: 4, message: "Exporting" },
      }),
    );
    expect(row.phase).toBe("disk full");
  });

  it("falls back to the humanized job type when progress has no message yet", () => {
    const row = toJobRowJob(
      makeJob({ type: "propose_page_kinds", progress: { current: 0, total: 0, message: "" } }),
    );
    expect(row.phase).toBe("Propose page kinds");
  });

  it("computes a 0-100 percentage from current/total", () => {
    const row = toJobRowJob(
      makeJob({ progress: { current: 1, total: 4, message: "" }, status: "running" }),
    );
    expect(row.pct).toBe(25);
  });

  it("does not divide by zero when total is 0", () => {
    const row = toJobRowJob(
      makeJob({ progress: { current: 0, total: 0, message: "" }, status: "running" }),
    );
    expect(row.pct).toBe(0);
  });

  it("falls back to 'No project' when project_id is null", () => {
    const row = toJobRowJob(makeJob({ project_id: null }));
    expect(row.project).toBe("No project");
  });
});

describe("toJobRowJobs", () => {
  it("caps finished jobs but always keeps every active job", () => {
    const active = Array.from({ length: 3 }, (_, i) =>
      makeJob({ id: `active-${String(i)}`, status: "running" }),
    );
    const finished = Array.from({ length: 30 }, (_, i) =>
      makeJob({ id: `done-${String(i)}`, status: "complete" }),
    );

    const rows = toJobRowJobs([...active, ...finished]);

    const activeIds = rows.filter((r) => r.status === "running").map((r) => r.id);
    expect(activeIds).toHaveLength(3);
    expect(rows.length).toBeLessThan(active.length + finished.length);
  });
});

describe("toPillActiveJobs", () => {
  it("includes only queued/running jobs — an empty surface must look empty", () => {
    const jobs = [
      makeJob({ id: "a", status: "queued" }),
      makeJob({ id: "b", status: "running" }),
      makeJob({ id: "c", status: "complete" }),
      makeJob({ id: "d", status: "error" }),
      makeJob({ id: "e", status: "cancelled" }),
    ];

    const active = toPillActiveJobs(jobs);

    expect(active.map((j) => j.id).sort()).toEqual(["a", "b"]);
  });

  it("returns an empty array when nothing is running — the pill must show idle", () => {
    const jobs = [makeJob({ status: "complete" }), makeJob({ id: "b", status: "cancelled" })];
    expect(toPillActiveJobs(jobs)).toEqual([]);
  });
});
