import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { server } from "../test/server";
import { ROUTES } from "../lib/routes";
import { dialogStore } from "../stores/dialog-store";
import { useUiPrefs } from "../stores/ui-prefs";

vi.mock("@pdomain/pdomain-ui/canvas", () => ({
  rectToDisplay: (bbox: { x: number; y: number; width: number; height: number }) => bbox,
  rectItemsToDisplay: <T,>(items: T[]) => items,
  RectOverlayLayer: () => <div data-testid="bbox-overlay" />,
  PageImageCanvas: ({
    children,
  }: {
    children?: { selection?: () => React.ReactNode; tool?: () => React.ReactNode };
  }) => (
    <div data-testid="image-viewport">
      {children?.selection?.()}
      {children?.tool?.()}
    </div>
  ),
}));

vi.mock("react-konva", () => ({
  Stage: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  Layer: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Rect: () => <div />,
  Image: () => <div />,
}));
vi.mock("use-image", () => ({ __esModule: true, default: () => [null, "loaded"] }));

import ProjectPage from "./ProjectPage";

function renderProjectPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/projects/p1/pages/pageno/1"]}>
        <Routes>
          <Route path={ROUTES.PROJECT_PAGE_NO} element={<ProjectPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function pageFixture(pageIndex: number) {
  return {
    project_id: "p1",
    page_index: pageIndex,
    line_matches: [],
    line_filter: "all",
    image_url: `/api/projects/p1/image/${String(pageIndex)}`,
    generation: 1,
    page_text_gt: `Working GT page ${String(pageIndex + 1)}`,
    page_text_ocr: `OCR page ${String(pageIndex + 1)}`,
  };
}

function sourceFixture(pageIndex: number) {
  const visible = `P3 source page ${String(pageIndex + 1)}`;
  return {
    project_id: "p1",
    page_index: pageIndex,
    page_key: `page-${String(pageIndex + 1)}.png`,
    available: true,
    f2: {
      raw_text: `<i>F2 source page ${String(pageIndex + 1)}</i>`,
      visible_text: `F2 source page ${String(pageIndex + 1)}`,
    },
    p3: { raw_text: visible, visible_text: visible },
    consolidated: {
      text: visible,
      runs: [{ text: visible, styles: [] }],
      layout_hints: [],
      unresolved: [],
    },
    warnings: [],
  };
}

describe("ProjectPage source tabs", () => {
  beforeEach(() => {
    dialogStore.reset();
    useUiPrefs.setState({ drawerOpen: true, rightPanelOpen: true });
  });

  it("keeps source previews scoped to page 1 → 2 → 3 → 1 and rejects a late page 2 response", async () => {
    let requestForPageTwoStarted = false;
    let releasePageTwo: (() => void) | undefined;
    const pageTwoResponse = new Promise<void>((resolve) => {
      releasePageTwo = resolve;
    });

    server.use(
      http.get("/api/projects/:pid", () =>
        HttpResponse.json({
          project_id: "p1",
          project_root: "/data/p1",
          image_paths: ["page-1.png", "page-2.png", "page-3.png"],
          ground_truth_map: {},
        }),
      ),
      http.get("/api/projects/:pid/pages/:idx", ({ params }) =>
        HttpResponse.json(pageFixture(Number(params["idx"]))),
      ),
      http.get("/api/projects/:pid/pages/:idx/source-text", async ({ params }) => {
        const pageIndex = Number(params["idx"]);
        if (pageIndex === 1) {
          requestForPageTwoStarted = true;
          await pageTwoResponse;
        }
        return HttpResponse.json(sourceFixture(pageIndex));
      }),
    );

    renderProjectPage();
    await screen.findByTestId("project-page");
    fireEvent.click(screen.getByTestId("text-tab-p3"));
    expect(await screen.findByTestId("text-panel-p3")).toHaveTextContent("P3 source page 1");

    fireEvent.click(await screen.findByTestId("nav-next-button"));
    await waitFor(() => expect(screen.getByTestId("nav-page-input")).toHaveValue(2));
    await waitFor(() => expect(requestForPageTwoStarted).toBe(true));
    expect(screen.getByTestId("source-preview-loading-p3")).toBeInTheDocument();
    expect(screen.queryByText("P3 source page 1")).not.toBeInTheDocument();

    fireEvent.click(await screen.findByTestId("nav-next-button"));
    await waitFor(() => expect(screen.getByTestId("nav-page-input")).toHaveValue(3));
    releasePageTwo?.();
    expect(await screen.findByTestId("text-panel-p3")).toHaveTextContent("P3 source page 3");
    expect(screen.queryByText("P3 source page 2")).not.toBeInTheDocument();

    fireEvent.click(await screen.findByTestId("nav-prev-button"));
    await waitFor(() => expect(screen.getByTestId("nav-page-input")).toHaveValue(2));
    fireEvent.click(await screen.findByTestId("nav-prev-button"));
    await waitFor(() => expect(screen.getByTestId("nav-page-input")).toHaveValue(1));
    expect(await screen.findByTestId("text-panel-p3")).toHaveTextContent("P3 source page 1");
  });
});
