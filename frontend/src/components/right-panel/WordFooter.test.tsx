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
type TypographyHeadResponse = components["schemas"]["TypographyHeadResponse"];

// ─── minimal page fixture ─────────────────────────────────────────────────────

const minPage: PagePayload = {
  project_id: "proj-1",
  page_index: 0,
  line_matches: [],
  line_filter: "all",
  generation: 0,
};

// P1-VALIDATE-GATE: a minimal, schema-complete TypographyHeadResponse fixture
// for the word's own review-gate tests below. `typography_reviewed` is the
// field the gate reads (docs/issues/
// 2026-09-18-the-per-word-validate-button-can-never-validate-a-word.md,
// option 2).
function headFixture(typographyReviewed: boolean): TypographyHeadResponse {
  return {
    project_id: "proj-1",
    page_index: 0,
    logical_page_id: "page",
    word_id: "w-2-1",
    page_sha256: "1".repeat(64),
    image_sha256: "2".repeat(64),
    text_sha256: "3".repeat(64),
    page_head_sha256: "4".repeat(64),
    word_revision: 0,
    text: "word",
    graphemes: ["w", "o", "r", "d"],
    grapheme_map_version: "server-graphemes-v1",
    taxonomy: { version: "server-taxonomy-v1", taxonomy_hash: "5".repeat(64), labels: [] },
    imported_text_validation_available: false,
    revision: 0,
    correction: null,
    typography_reviewed: typographyReviewed,
    head_token: "6".repeat(64),
  };
}

// ─── wrapper ──────────────────────────────────────────────────────────────────

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function renderFooter(isValidated = false, wordId?: string | null) {
  return render(
    <WordFooter
      page={minPage}
      projectId="proj-1"
      pageIndex={0}
      lineIndex={2}
      wordIndex={1}
      isValidated={isValidated}
      wordId={wordId}
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

  it("shows the page-wide review summary without gating on it", async () => {
    server.use(
      http.get("/api/projects/proj-1/pages/0/typography/review", () =>
        HttpResponse.json({
          project_id: "proj-1",
          page_index: 0,
          logical_page_id: "page",
          reviewed_words: 1,
          text_reviewed_words: 1,
          typography_reviewed_words: 0,
          blocked_words: 1,
          total_words: 2,
          complete: false,
          heads: [],
        }),
      ),
    );
    renderFooter(false);
    expect(await screen.findByText(/Text 1\/2 · Typography 0\/2/)).toBeInTheDocument();
  });

  // P1-VALIDATE-GATE (docs/issues/
  // 2026-09-18-the-per-word-validate-button-can-never-validate-a-word.md):
  // the gate reads *this word's own* typography review
  // (`TypographyHeadResponse.typography_reviewed`), not the whole page's
  // completion — gating on the page made the button permanently disabled for
  // the first unvalidated word, since page completion itself required every
  // word already validated.
  it("blocks validating a word whose own typography review isn't complete", async () => {
    server.use(
      http.get("/api/projects/proj-1/pages/0/typography/words/w-2-1/head", () =>
        HttpResponse.json(headFixture(false)),
      ),
    );
    renderFooter(false, "w-2-1");
    await waitFor(() => {
      expect(screen.getByTestId("word-footer-validate")).toBeDisabled();
    });
  });

  it("allows validating a word once its own typography review is complete", async () => {
    server.use(
      http.get("/api/projects/proj-1/pages/0/typography/words/w-2-1/head", () =>
        HttpResponse.json(headFixture(true)),
      ),
    );
    renderFooter(false, "w-2-1");
    await waitFor(() => {
      expect(screen.getByTestId("word-footer-validate")).toBeEnabled();
    });
  });

  it("does not gate on typography review when the word has no stable id", async () => {
    renderFooter(false, null);
    // No `wordId` means `useTypographyHead` never fires (enabled: false), so
    // there's nothing to await — assert synchronously that the button isn't
    // blocked by a gate that can't apply to this word.
    expect(screen.getByTestId("word-footer-validate")).toBeEnabled();
  });

  it("always allows unvalidating, regardless of this word's typography review", async () => {
    server.use(
      http.get("/api/projects/proj-1/pages/0/typography/words/w-2-1/head", () =>
        HttpResponse.json(headFixture(false)),
      ),
    );
    renderFooter(true, "w-2-1");
    await waitFor(() => {
      expect(screen.getByTestId("word-footer-validate")).toBeEnabled();
    });
  });

  // Proves the full loop the issue reported as broken: validate a first word
  // on a fresh page, unvalidate it, and validate it again — end to end
  // through the real click handler and mutation, not by reasoning about the
  // disabled expression.
  it("validates, unvalidates, and revalidates the same word end to end", async () => {
    let currentIsValidated = false;
    const postedBodies: unknown[] = [];
    server.use(
      http.get("/api/projects/proj-1/pages/0/typography/words/w-2-1/head", () =>
        HttpResponse.json(headFixture(true)),
      ),
      http.post("/api/projects/proj-1/pages/0/words/2/1/validated", async ({ request }) => {
        const body = (await request.json()) as { validated: boolean };
        postedBodies.push(body);
        currentIsValidated = body.validated;
        return HttpResponse.json(minPage);
      }),
    );
    const user = userEvent.setup();
    const { rerender } = render(
      <Wrapper>
        <WordFooter
          page={minPage}
          projectId="proj-1"
          pageIndex={0}
          lineIndex={2}
          wordIndex={1}
          isValidated={currentIsValidated}
          wordId="w-2-1"
        />
      </Wrapper>,
    );

    // 1. Validate the first (unvalidated) word — the direction the issue
    //    found permanently disabled.
    await waitFor(() => {
      expect(screen.getByTestId("word-footer-validate")).toBeEnabled();
    });
    await user.click(screen.getByTestId("word-footer-validate"));
    await waitFor(() => {
      expect(postedBodies).toEqual([{ validated: true }]);
    });
    rerender(
      <Wrapper>
        <WordFooter
          page={minPage}
          projectId="proj-1"
          pageIndex={0}
          lineIndex={2}
          wordIndex={1}
          isValidated={currentIsValidated}
          wordId="w-2-1"
        />
      </Wrapper>,
    );
    expect(screen.getByTestId("word-footer-validate")).toHaveTextContent("Validated");

    // 2. Unvalidate it — always allowed.
    await user.click(screen.getByTestId("word-footer-validate"));
    await waitFor(() => {
      expect(postedBodies).toEqual([{ validated: true }, { validated: false }]);
    });
    rerender(
      <Wrapper>
        <WordFooter
          page={minPage}
          projectId="proj-1"
          pageIndex={0}
          lineIndex={2}
          wordIndex={1}
          isValidated={currentIsValidated}
          wordId="w-2-1"
        />
      </Wrapper>,
    );
    expect(screen.getByTestId("word-footer-validate")).toHaveTextContent("Validate");
    expect(screen.getByTestId("word-footer-validate")).not.toHaveTextContent("Validated");

    // 3. Validate it again — this is the step the original gate made
    //    impossible: once unvalidated, the button could never come back.
    await waitFor(() => {
      expect(screen.getByTestId("word-footer-validate")).toBeEnabled();
    });
    await user.click(screen.getByTestId("word-footer-validate"));
    await waitFor(() => {
      expect(postedBodies).toEqual([
        { validated: true },
        { validated: false },
        { validated: true },
      ]);
    });
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
