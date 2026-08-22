import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ROUTES } from "../lib/routes";
import { server } from "../test/server";
import TypographyWorklistPage from "./TypographyWorklistPage";

vi.mock("../components/right-panel/sections/TypographySection", () => ({
  TypographySection: ({ wordId }: { wordId?: string | null }) => (
    <div data-testid="mounted-typography-section">{wordId ?? "no selection"}</div>
  ),
}));

function renderPage() {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={["/projects/project-1/pages/pageno/3/typography"]}>
        <Routes>
          <Route path={ROUTES.PROJECT_TYPOGRAPHY_PAGE_NO} element={<TypographyWorklistPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TypographyWorklistPage", () => {
  it("shows producer order and treats imported text review as unreviewed", async () => {
    server.use(
      http.get("/api/projects/project-1/pages/2/typography/worklist", () =>
        HttpResponse.json({
          project_id: "project-1",
          page_index: 2,
          logical_page_id: "pgdp:project-1:003.png",
          words: [
            {
              word_id: "producer-word-b",
              text: "First",
              source_review_state: "reviewed",
              text_reviewed: false,
              typography_reviewed: false,
              decision: null,
            },
            {
              word_id: "producer-word-a",
              text: "Second",
              source_review_state: "reviewed_regular",
              text_reviewed: false,
              typography_reviewed: true,
              decision: "reviewed_regular",
            },
          ],
        }),
      ),
    );

    renderPage();

    const rows = await screen.findAllByTestId(/typography-worklist-word-/);
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringContaining("First"),
      expect.stringContaining("Second"),
    ]);
    expect(rows[0]).toHaveTextContent("Source: reviewed");
    expect(rows[0]).toHaveTextContent("Text: unreviewed");
    expect(rows[1]).toHaveTextContent("Typography: reviewed regular");
    expect(screen.getByTestId("mounted-typography-section")).toHaveTextContent("producer-word-b");
  });

  it("selects by the exact producer word ID without the OCR selection store", async () => {
    server.use(
      http.get("/api/projects/project-1/pages/2/typography/worklist", () =>
        HttpResponse.json({
          project_id: "project-1",
          page_index: 2,
          logical_page_id: "pgdp:project-1:003.png",
          words: [
            {
              word_id: "producer-word-1",
              text: "One",
              source_review_state: "reviewed",
              text_reviewed: false,
              typography_reviewed: false,
              decision: null,
            },
            {
              word_id: "producer-word-2",
              text: "Two",
              source_review_state: "reviewed",
              text_reviewed: false,
              typography_reviewed: false,
              decision: null,
            },
          ],
        }),
      ),
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: /Two/ }));

    expect(screen.getByTestId("mounted-typography-section")).toHaveTextContent("producer-word-2");
  });
});
