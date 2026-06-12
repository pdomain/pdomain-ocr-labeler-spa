// WordFooter.test.tsx — P2.f tests for the validate/skip/delete footer.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { WordFooter } from "./WordFooter";
import * as selectionStore from "../../stores/selection-store";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];

// ─── minimal page fixture ─────────────────────────────────────────────────────

const minPage: PagePayload = {
  project_id: "proj-1",
  page_index: 0,
  line_matches: [],
  line_filter: "all",
  generation: 0,
};

// ─── wrapper ──────────────────────────────────────────────────────────────────

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function renderFooter(isValidated = false) {
  return render(
    <WordFooter
      page={minPage}
      projectId="proj-1"
      pageIndex={0}
      lineIndex={2}
      wordIndex={1}
      isValidated={isValidated}
    />,
    { wrapper: Wrapper },
  );
}

// ─── tests ────────────────────────────────────────────────────────────────────

describe("WordFooter (P2.f)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the footer container", () => {
    renderFooter();
    expect(screen.getByTestId("word-footer")).toBeInTheDocument();
  });

  it("renders all three action buttons", () => {
    renderFooter();
    expect(screen.getByTestId("word-footer-validate")).toBeInTheDocument();
    expect(screen.getByTestId("word-footer-skip")).toBeInTheDocument();
    expect(screen.getByTestId("word-footer-delete")).toBeInTheDocument();
  });

  it("shows 'Validate' label when word is not validated", () => {
    renderFooter(false);
    expect(screen.getByTestId("word-footer-validate")).toHaveTextContent("Validate");
  });

  it("shows '✓ Validated' label when word is validated", () => {
    renderFooter(true);
    expect(screen.getByTestId("word-footer-validate")).toHaveTextContent("Validated");
  });

  it("calls walkSibling('next', page) when Skip is clicked", async () => {
    const spy = vi.spyOn(selectionStore, "walkSibling").mockImplementation(() => {});
    renderFooter();
    await userEvent.click(screen.getByTestId("word-footer-skip"));
    expect(spy).toHaveBeenCalledWith("next", minPage);
  });

  it("opens ConfirmDialog when Delete is clicked", async () => {
    renderFooter();
    expect(screen.queryByTestId("confirm-dialog")).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId("word-footer-delete"));
    expect(screen.getByTestId("confirm-dialog")).toBeInTheDocument();
  });

  it("closes ConfirmDialog when Cancel is clicked", async () => {
    renderFooter();
    await userEvent.click(screen.getByTestId("word-footer-delete"));
    await userEvent.click(screen.getByTestId("confirm-dialog-cancel"));
    expect(screen.queryByTestId("confirm-dialog")).not.toBeInTheDocument();
  });

  // P1.3 (B-61): confirming Delete must POST the real words/delete-batch
  // route — the page-scope /delete endpoint is a 501 stub that never
  // deleted anything (confirm-then-delete-nothing).
  it("confirming Delete POSTs words/delete-batch with the word tuple", async () => {
    let body: unknown;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/delete-batch", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(minPage);
      }),
    );
    renderFooter();
    await userEvent.click(screen.getByTestId("word-footer-delete"));
    await userEvent.click(screen.getByTestId("confirm-dialog-confirm"));
    await waitFor(() => expect(body).toEqual({ scope: "word", word_indices: [[2, 1]] }));
  });
});
