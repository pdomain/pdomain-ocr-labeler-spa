// HeaderBar.test.tsx — tests for the simplified HeaderBar.
//
// Simplified layout (2026-05-16):
//   Left:   logo badge + "OCR Labeler" text (link to /) + "Projects" link to /
//           [+ "/" + project-name chip when projectName prop is set]
//   Center: navSlot (optional) + actionsSlot (optional)
//   Right:  [header-metrics-strip (project route only)] + ThemeChips (Dark/Light/System)
//   Hidden: driver-contract stub div (display:none)
//
// Removed from HeaderBar: ProjectLoadControls, MetricsStrip, QuickSearch,
// dialog trigger buttons (ocr-config, export, hotkey-help), UserMenu.

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import HeaderBar from "./HeaderBar";
import type { PageMetrics } from "./HeaderBar";

// --- helpers -----------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

interface RenderOpts {
  route?: string;
  navSlot?: React.ReactNode;
  actionsSlot?: React.ReactNode;
  projectName?: string | null;
  pageMetrics?: PageMetrics | null;
}

function renderHeaderBar({
  route = "/",
  navSlot,
  actionsSlot,
  projectName,
  pageMetrics,
}: RenderOpts = {}) {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <HeaderBar
          {...(navSlot !== undefined && { navSlot })}
          {...(actionsSlot !== undefined && { actionsSlot })}
          {...(projectName !== undefined && { projectName })}
          {...(pageMetrics !== undefined && { pageMetrics })}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// --- structure + testids -----------------------------------------------------

describe("HeaderBar: structure", () => {
  it("renders header-bar testid", async () => {
    renderHeaderBar();
    expect(screen.getByTestId("header-bar")).toBeInTheDocument();
  });

  it("renders header-logo link pointing to /", async () => {
    renderHeaderBar({ route: "/projects/p1/pages/pageno/1" });
    const logo = screen.getByTestId("header-logo");
    expect(logo.tagName.toLowerCase()).toBe("a");
    expect(logo).toHaveAttribute("href", "/");
  });

  it("renders header-logo-badge", async () => {
    renderHeaderBar();
    expect(screen.getByTestId("header-logo-badge")).toBeInTheDocument();
  });

  it("renders projects-home-link pointing to /", async () => {
    renderHeaderBar({ route: "/projects/p1/pages/pageno/1" });
    const link = screen.getByTestId("projects-home-link");
    expect(link.tagName.toLowerCase()).toBe("a");
    expect(link).toHaveAttribute("href", "/");
    expect(link).toHaveTextContent("Projects");
  });

  it("has h-14 height class (56px)", async () => {
    renderHeaderBar();
    const header = screen.getByTestId("header-bar");
    expect(header.className).toMatch(/h-14/);
  });

  it("does NOT render project-load controls (removed)", async () => {
    renderHeaderBar();
    expect(screen.queryByTestId("project-select")).not.toBeInTheDocument();
    expect(screen.queryByTestId("load-project-button")).not.toBeInTheDocument();
    expect(screen.queryByTestId("source-folder-button")).not.toBeInTheDocument();
  });

  it("does NOT render legacy metrics-strip testid (removed)", async () => {
    renderHeaderBar({ route: "/projects/p1/pages/pageno/1" });
    expect(screen.queryByTestId("metrics-strip")).not.toBeInTheDocument();
  });

  it("does NOT render header-metrics-strip when pageMetrics is null", async () => {
    renderHeaderBar({ route: "/projects/p1/pages/pageno/1", pageMetrics: null });
    expect(screen.queryByTestId("header-metrics-strip")).not.toBeInTheDocument();
  });

  it("does NOT render header-project-name when projectName is null", async () => {
    renderHeaderBar({ route: "/projects/p1/pages/pageno/1", projectName: null });
    expect(screen.queryByTestId("header-project-name")).not.toBeInTheDocument();
  });

  it("does NOT render quick-search (removed)", async () => {
    renderHeaderBar();
    expect(screen.queryByTestId("quick-search")).not.toBeInTheDocument();
  });

  it("does NOT render dialog trigger buttons (removed)", async () => {
    renderHeaderBar();
    expect(screen.queryByTestId("ocr-config-trigger-button")).not.toBeInTheDocument();
    expect(screen.queryByTestId("export-trigger-button")).not.toBeInTheDocument();
    expect(screen.queryByTestId("hotkey-help-trigger-button")).not.toBeInTheDocument();
  });

  it("does NOT render user-menu (removed)", async () => {
    renderHeaderBar();
    expect(screen.queryByTestId("user-menu-trigger")).not.toBeInTheDocument();
  });
});

// --- theme chips -------------------------------------------------------------

describe("HeaderBar: theme chips", () => {
  it("renders theme-chips radiogroup", async () => {
    renderHeaderBar();
    expect(screen.getByTestId("theme-chips")).toBeInTheDocument();
  });

  it("renders Dark, Light, System chip buttons", async () => {
    renderHeaderBar();
    expect(screen.getByTestId("theme-chip-dark")).toBeInTheDocument();
    expect(screen.getByTestId("theme-chip-light")).toBeInTheDocument();
    expect(screen.getByTestId("theme-chip-system")).toBeInTheDocument();
  });

  it("clicking a chip changes aria-checked", async () => {
    renderHeaderBar();
    const lightChip = screen.getByTestId("theme-chip-light");
    await userEvent.click(lightChip);
    expect(lightChip).toHaveAttribute("aria-checked", "true");
  });
});

// --- slots -------------------------------------------------------------------

describe("HeaderBar: navSlot and actionsSlot", () => {
  it("renders navSlot content when provided", async () => {
    renderHeaderBar({ navSlot: <span data-testid="nav-slot-content">Nav</span> });
    expect(screen.getByTestId("nav-slot-content")).toBeInTheDocument();
  });

  it("does not render navSlot content when not provided", async () => {
    renderHeaderBar();
    expect(screen.queryByTestId("nav-slot-content")).not.toBeInTheDocument();
  });

  it("renders actionsSlot content when provided", async () => {
    renderHeaderBar({ actionsSlot: <span data-testid="actions-slot-content">Actions</span> });
    expect(screen.getByTestId("actions-slot-content")).toBeInTheDocument();
  });

  it("does not render actionsSlot content when not provided", async () => {
    renderHeaderBar();
    expect(screen.queryByTestId("actions-slot-content")).not.toBeInTheDocument();
  });
});

// --- project breadcrumb (P1.a) -----------------------------------------------

describe("HeaderBar: project breadcrumb", () => {
  it("renders header-project-name when projectName is provided", async () => {
    renderHeaderBar({ projectName: "my-book-project" });
    const chip = screen.getByTestId("header-project-name");
    expect(chip).toBeInTheDocument();
    expect(chip).toHaveTextContent("my-book-project");
  });

  it("does NOT render header-project-name when projectName is empty string", async () => {
    renderHeaderBar({ projectName: "" });
    expect(screen.queryByTestId("header-project-name")).not.toBeInTheDocument();
  });

  it("does NOT render breadcrumb separator when projectName is null", async () => {
    renderHeaderBar({ projectName: null });
    // The "/" separator span has text content "/"; ensure it's absent when no project.
    expect(screen.queryByTestId("header-project-name")).not.toBeInTheDocument();
  });
});

// --- metrics strip (P1.a) ----------------------------------------------------

describe("HeaderBar: metrics strip", () => {
  const metrics: PageMetrics = {
    total: 12,
    exact: 8,
    fuzzy: 3,
    mismatch: 1,
    validated: 4,
  };

  it("renders header-metrics-strip when pageMetrics has total > 0", async () => {
    renderHeaderBar({ pageMetrics: metrics });
    expect(screen.getByTestId("header-metrics-strip")).toBeInTheDocument();
  });

  it("shows word count in the strip", async () => {
    renderHeaderBar({ pageMetrics: metrics });
    expect(screen.getByTestId("header-metrics-strip")).toHaveTextContent("12 words");
  });

  it("shows exact count in the strip", async () => {
    renderHeaderBar({ pageMetrics: metrics });
    expect(screen.getByTestId("header-metrics-strip")).toHaveTextContent("8 exact");
  });

  it("shows fuzzy count in the strip", async () => {
    renderHeaderBar({ pageMetrics: metrics });
    expect(screen.getByTestId("header-metrics-strip")).toHaveTextContent("3 fuzzy");
  });

  it("shows mismatch count with ✗ in the strip", async () => {
    renderHeaderBar({ pageMetrics: metrics });
    expect(screen.getByTestId("header-metrics-strip")).toHaveTextContent("1 ✗");
  });

  it("shows validated fraction in the strip", async () => {
    renderHeaderBar({ pageMetrics: metrics });
    expect(screen.getByTestId("header-metrics-strip")).toHaveTextContent("4/12 validated");
  });

  it("shows glyphs-reviewed fraction when glyphs_reviewed is provided (spec §8)", async () => {
    const withGlyphs: PageMetrics = { ...metrics, glyphs_reviewed: 7 };
    renderHeaderBar({ pageMetrics: withGlyphs });
    expect(screen.getByTestId("header-metrics-strip")).toHaveTextContent("7/12 glyphs");
  });

  it("does NOT show glyphs metric when glyphs_reviewed is absent", async () => {
    renderHeaderBar({ pageMetrics: metrics });
    expect(screen.getByTestId("header-metrics-strip")).not.toHaveTextContent("glyphs");
  });

  it("does NOT render header-metrics-strip when total is 0", async () => {
    const zeroMetrics: PageMetrics = { total: 0, exact: 0, fuzzy: 0, mismatch: 0, validated: 0 };
    renderHeaderBar({ pageMetrics: zeroMetrics });
    expect(screen.queryByTestId("header-metrics-strip")).not.toBeInTheDocument();
  });

  it("does NOT render header-metrics-strip when pageMetrics is undefined", async () => {
    renderHeaderBar();
    expect(screen.queryByTestId("header-metrics-strip")).not.toBeInTheDocument();
  });
});

// --- driver-contract stubs (display:none) ------------------------------------

describe("HeaderBar: driver-contract stubs", () => {
  it("stub nav buttons are in the DOM (display:none)", async () => {
    renderHeaderBar();
    const prev = screen.getByTestId("nav-prev-button");
    expect(prev).toBeInTheDocument();
    expect(prev).toHaveAttribute("data-testid-stub", "true");
  });

  it("stub source-folder elements are in the DOM", async () => {
    renderHeaderBar();
    expect(screen.getByTestId("source-folder-path-input")).toBeInTheDocument();
    expect(screen.getByTestId("source-folder-apply-button")).toBeInTheDocument();
  });

  it("stub ocr-config elements are in the DOM", async () => {
    renderHeaderBar();
    expect(screen.getByTestId("ocr-detection-model-select")).toBeInTheDocument();
    expect(screen.getByTestId("ocr-config-apply-button")).toBeInTheDocument();
  });
});
