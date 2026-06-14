// HeaderBar.test.tsx — tests for the chrome-only HeaderBar.
//
// M1 (D-047 / D-048, 2026-06-14): HeaderBar is slimmed to pure chrome. The
// document/page-scoped controls moved out:
//   - navSlot / actionsSlot / metrics → WorkspaceToolbar band
//   - searchSlot (QuickSearch) → Drawer worklist-header slot
//   - theme chips → pdomain-ui SettingsModal Appearance panel (D-048)
//
// Visible layout (chrome only):
//   Left: logo badge + "OCR Labeler" + "Projects" link
//         [+ "/" + project-name chip] [+ resolved project-root path label]
//   The AppShell injects LauncherSlot + SettingsSlot ⚙ into its header zone.
//
// The `display:none` driver-contract stub div (D-046) is retained: source-folder
// + OCR-config field stubs and nav stubs stay reachable on every route. These
// stubs carry `data-testid-stub="true"`; the chrome-only assertions below check
// that no NON-stub document control is present in the header.

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import HeaderBar from "./HeaderBar";

// --- helpers -----------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

interface RenderOpts {
  route?: string;
  projectName?: string | null;
  projectRoot?: string | null;
}

/** Renders current pathname + navigation state so tests can assert on both
 * after a Link click (LocationSpy pattern — see agent memory: mocking
 * react-router-dom breaks useParams; read useLocation() instead). */
function LocationSpy() {
  const location = useLocation();
  const state = location.state as { skipSessionRedirect?: boolean } | null;
  return (
    <div data-testid="location-spy">
      path={location.pathname};skipSessionRedirect=
      {state?.skipSessionRedirect ? "true" : "false"}
    </div>
  );
}

function renderHeaderBar({ route = "/", projectName, projectRoot }: RenderOpts = {}) {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <HeaderBar
          {...(projectName !== undefined && { projectName })}
          {...(projectRoot !== undefined && { projectRoot })}
        />
        <LocationSpy />
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

  it("projects-home-link navigation carries skipSessionRedirect state (P4.1 / A-02)", async () => {
    // Without skipSessionRedirect, RootPage's session-redirect bounces the
    // user straight back to the loaded project — the grid is unreachable.
    const user = userEvent.setup();
    renderHeaderBar({ route: "/projects/p1/pages/pageno/1" });
    await user.click(screen.getByTestId("projects-home-link"));
    const spy = screen.getByTestId("location-spy");
    expect(spy).toHaveTextContent("path=/");
    expect(spy).toHaveTextContent("skipSessionRedirect=true");
  });

  it("header-logo navigation carries skipSessionRedirect state (P4.1 / A-02)", async () => {
    const user = userEvent.setup();
    renderHeaderBar({ route: "/projects/p1/pages/pageno/1" });
    await user.click(screen.getByTestId("header-logo"));
    const spy = screen.getByTestId("location-spy");
    expect(spy).toHaveTextContent("path=/");
    expect(spy).toHaveTextContent("skipSessionRedirect=true");
  });

  it("has h-14 height class (56px)", async () => {
    renderHeaderBar();
    const header = screen.getByTestId("header-bar");
    expect(header.className).toMatch(/h-14/);
  });
});

// --- chrome-only: no visible document/page-scoped controls (D-047) -----------

describe("HeaderBar: chrome-only (D-047)", () => {
  /** A "real" (non-stub) testid is one without data-testid-stub="true". */
  function queryRealTestId(testid: string): HTMLElement | null {
    const matches = screen.queryAllByTestId(testid);
    return matches.find((el) => el.getAttribute("data-testid-stub") !== "true") ?? null;
  }

  it("does NOT render the metrics strip in the header", async () => {
    renderHeaderBar({ route: "/projects/p1/pages/pageno/1" });
    expect(screen.queryByTestId("header-metrics-strip")).not.toBeInTheDocument();
    expect(screen.queryByTestId("metrics-strip")).not.toBeInTheDocument();
  });

  it("does NOT render theme chips (relocated to SettingsModal Appearance panel — D-048)", async () => {
    renderHeaderBar();
    expect(screen.queryByTestId("theme-chips")).not.toBeInTheDocument();
    expect(screen.queryByTestId("theme-chip-dark")).not.toBeInTheDocument();
    expect(screen.queryByTestId("theme-chip-light")).not.toBeInTheDocument();
    expect(screen.queryByTestId("theme-chip-system")).not.toBeInTheDocument();
  });

  it("does NOT render QuickSearch in the header (relocated to drawer)", async () => {
    renderHeaderBar();
    expect(screen.queryByTestId("quick-search")).not.toBeInTheDocument();
    expect(screen.queryByTestId("quick-search-input")).not.toBeInTheDocument();
  });

  it("does NOT render real (non-stub) page-action controls in the header", async () => {
    renderHeaderBar({ route: "/projects/p1/pages/pageno/1" });
    expect(screen.queryByTestId("page-actions-compact")).not.toBeInTheDocument();
    expect(queryRealTestId("page-actions-compact-save-page")).toBeNull();
  });

  it("does NOT render nav controls in the header (D-049: nav stubs removed)", async () => {
    // D-049: nav-* stubs removed from HeaderBar. The real
    // ProjectNavigationControls in WorkspaceToolbar leftSlot is the single
    // source of truth.
    renderHeaderBar({ route: "/projects/p1/pages/pageno/1" });
    expect(screen.queryByTestId("nav-prev-button")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-page-input")).not.toBeInTheDocument();
  });

  it("does NOT render project-load controls (removed)", async () => {
    renderHeaderBar();
    expect(screen.queryByTestId("project-select")).not.toBeInTheDocument();
    expect(screen.queryByTestId("load-project-button")).not.toBeInTheDocument();
    expect(screen.queryByTestId("source-folder-button")).not.toBeInTheDocument();
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

  it("does NOT render header-project-name when projectName is null", async () => {
    renderHeaderBar({ projectName: null });
    expect(screen.queryByTestId("header-project-name")).not.toBeInTheDocument();
  });
});

// ─── S6.2: resolved project path label ────────────────────────────────────────

describe("HeaderBar: S6.2 project-root-label", () => {
  it("renders project-root-label when projectRoot is provided", () => {
    renderHeaderBar({ projectName: "book1", projectRoot: "/srv/projects/book1" });
    const label = screen.getByTestId("project-root-label");
    expect(label).toBeInTheDocument();
    expect(label).toHaveTextContent("/srv/projects/book1");
  });

  it("project-root-label is NOT sr-only (visually rendered)", () => {
    renderHeaderBar({ projectName: "book1", projectRoot: "/srv/projects/book1" });
    const label = screen.getByTestId("project-root-label");
    expect(label.className).not.toContain("sr-only");
  });

  it("does NOT render project-root-label when projectRoot is null", () => {
    renderHeaderBar({ projectName: "book1", projectRoot: null });
    expect(screen.queryByTestId("project-root-label")).not.toBeInTheDocument();
  });

  it("does NOT render project-root-label on root route (no projectRoot)", () => {
    renderHeaderBar();
    expect(screen.queryByTestId("project-root-label")).not.toBeInTheDocument();
  });
});

// --- driver-contract stubs (display:none) — retained per D-046 ----------------
// D-049: nav-* stubs removed from HeaderBar. Source-folder + OCR-config
// field stubs remain (driver-contract §2.2/§2.3).

describe("HeaderBar: driver-contract stubs (D-046/D-049)", () => {
  it("D-049: nav stubs are NO LONGER in the DOM (removed per D-049)", async () => {
    renderHeaderBar();
    // Nav stubs were removed — the real ProjectNavigationControls in
    // WorkspaceToolbar is the single source of truth.
    expect(screen.queryByTestId("nav-prev-button")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-next-button")).not.toBeInTheDocument();
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
