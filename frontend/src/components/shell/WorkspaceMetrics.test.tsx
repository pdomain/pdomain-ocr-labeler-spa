// WorkspaceMetrics.test.tsx — per-page match metrics strip.
//
// M1 (D-047): the metrics strip moves out of HeaderBar into the workspace
// toolbar rightSlot. The `header-metrics-strip` testid is preserved unchanged
// for driver continuity — only the mount point changes.

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { WorkspaceMetrics, type PageMetrics } from "./WorkspaceMetrics";

const metrics: PageMetrics = {
  total: 12,
  exact: 8,
  fuzzy: 3,
  mismatch: 1,
  validated: 4,
};

describe("WorkspaceMetrics", () => {
  it("renders header-metrics-strip when total > 0", () => {
    render(<WorkspaceMetrics pageMetrics={metrics} />);
    expect(screen.getByTestId("header-metrics-strip")).toBeInTheDocument();
  });

  it("shows word / exact / fuzzy / mismatch / validated counts", () => {
    render(<WorkspaceMetrics pageMetrics={metrics} />);
    const strip = screen.getByTestId("header-metrics-strip");
    expect(strip).toHaveTextContent("12 words");
    expect(strip).toHaveTextContent("8 exact");
    expect(strip).toHaveTextContent("3 fuzzy");
    expect(strip).toHaveTextContent("1 ✗");
    expect(strip).toHaveTextContent("4/12 validated");
  });

  it("shows glyphs-reviewed fraction when provided", () => {
    render(<WorkspaceMetrics pageMetrics={{ ...metrics, glyphs_reviewed: 7 }} />);
    expect(screen.getByTestId("header-metrics-strip")).toHaveTextContent("7/12 glyphs");
  });

  it("does NOT show glyphs metric when glyphs_reviewed is absent", () => {
    render(<WorkspaceMetrics pageMetrics={metrics} />);
    expect(screen.getByTestId("header-metrics-strip")).not.toHaveTextContent("glyphs");
  });

  it("renders nothing when total is 0", () => {
    render(<WorkspaceMetrics pageMetrics={{ ...metrics, total: 0 }} />);
    expect(screen.queryByTestId("header-metrics-strip")).not.toBeInTheDocument();
  });

  it("renders nothing when pageMetrics is null", () => {
    render(<WorkspaceMetrics pageMetrics={null} />);
    expect(screen.queryByTestId("header-metrics-strip")).not.toBeInTheDocument();
  });
});
