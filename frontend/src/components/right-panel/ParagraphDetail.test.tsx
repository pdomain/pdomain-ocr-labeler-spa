// ParagraphDetail.test.tsx — Lane D / Task D1.
// Paragraph-scope right-panel actions: merge, delete, split-after-line,
// copy GT↔OCR, validate / unvalidate. Each button fires its real backend route.

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { ParagraphDetail } from "./ParagraphDetail";
import { clearSelection, selectPara } from "../../stores/selection-store";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function makePage(): PagePayload {
  return {
    project_id: "p1",
    page_index: 0,
    line_filter: "all",
    generation: 0,
    line_matches: [
      {
        line_index: 0,
        paragraph_index: 0,
        ocr_line_text: "hello",
        ground_truth_line_text: "hello",
        word_matches: [
          {
            line_index: 0,
            word_index: 0,
            ocr_text: "hello",
            ground_truth_text: "hello",
            match_status: "exact",
            normalized_match: false,
            is_validated: false,
            bbox: { x: 0, y: 0, width: 0, height: 0 },
          },
        ],
        overall_match_status: "exact",
        exact_count: 1,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: 1,
        is_fully_validated: false,
      },
      {
        line_index: 1,
        paragraph_index: 0,
        ocr_line_text: "world",
        ground_truth_line_text: "world",
        word_matches: [
          {
            line_index: 1,
            word_index: 0,
            ocr_text: "world",
            ground_truth_text: "world",
            match_status: "exact",
            normalized_match: false,
            is_validated: false,
            bbox: { x: 0, y: 0, width: 0, height: 0 },
          },
        ],
        overall_match_status: "exact",
        exact_count: 1,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: 1,
        is_fully_validated: false,
      },
    ],
  };
}

function renderWithQuery(ui: React.ReactElement) {
  const qc = makeQueryClient();
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("ParagraphDetail (Lane D / D1)", () => {
  beforeEach(() => {
    clearSelection();
  });

  it("shows 'No paragraph selected' when nothing is selected", () => {
    renderWithQuery(<ParagraphDetail page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("paragraph-detail")).toHaveTextContent(/no paragraph/i);
  });

  it("renders all paragraph-scope action buttons when a paragraph is selected", () => {
    selectPara(0);
    renderWithQuery(<ParagraphDetail page={makePage()} projectId="p1" pageIndex={0} />);
    for (const id of [
      "para-merge",
      "para-delete",
      "para-split-after-line",
      "para-copy-gt-to-ocr",
      "para-copy-ocr-to-gt",
      "para-validate",
      "para-unvalidate",
    ]) {
      expect(screen.getByTestId(id)).toBeInTheDocument();
    }
  });

  it("para-merge POSTs paragraphs/merge", async () => {
    const user = userEvent.setup();
    let hit: unknown;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/paragraphs/merge", async ({ request }) => {
        hit = await request.json();
        return HttpResponse.json(makePage());
      }),
    );
    selectPara(0);
    renderWithQuery(<ParagraphDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("para-merge"));
    await waitFor(() => expect(hit).toBeDefined());
    expect((hit as { paragraph_indices: number[] }).paragraph_indices).toEqual([0, 1]);
  });

  it("para-delete POSTs paragraphs/{pi}/delete", async () => {
    const user = userEvent.setup();
    let hit = false;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/paragraphs/:pi/delete", () => {
        hit = true;
        return HttpResponse.json(makePage());
      }),
    );
    selectPara(0);
    renderWithQuery(<ParagraphDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("para-delete"));
    await waitFor(() => expect(hit).toBe(true));
  });

  it("para-split-after-line POSTs paragraphs/{pi}/split-after-line", async () => {
    const user = userEvent.setup();
    let hit: unknown;
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/paragraphs/:pi/split-after-line",
        async ({ request }) => {
          hit = await request.json();
          return HttpResponse.json(makePage());
        },
      ),
    );
    selectPara(0);
    renderWithQuery(<ParagraphDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("para-split-after-line"));
    await waitFor(() => expect(hit).toBeDefined());
    expect((hit as { after_line_index: number }).after_line_index).toBe(0);
  });

  it("para-copy-gt-to-ocr POSTs paragraphs/{pi}/copy-gt-to-ocr", async () => {
    const user = userEvent.setup();
    let hit = false;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/paragraphs/:pi/copy-gt-to-ocr", () => {
        hit = true;
        return HttpResponse.json(makePage());
      }),
    );
    selectPara(0);
    renderWithQuery(<ParagraphDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("para-copy-gt-to-ocr"));
    await waitFor(() => expect(hit).toBe(true));
  });

  it("para-copy-ocr-to-gt POSTs paragraphs/{pi}/copy-ocr-to-gt", async () => {
    const user = userEvent.setup();
    let hit = false;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/paragraphs/:pi/copy-ocr-to-gt", () => {
        hit = true;
        return HttpResponse.json(makePage());
      }),
    );
    selectPara(0);
    renderWithQuery(<ParagraphDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("para-copy-ocr-to-gt"));
    await waitFor(() => expect(hit).toBe(true));
  });

  it("para-validate POSTs words/validate-batch scope=paragraph validated=true", async () => {
    const user = userEvent.setup();
    let body: { scope: string; validated: boolean; paragraph_indices: number[] } | undefined;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/validate-batch", async ({ request }) => {
        body = (await request.json()) as typeof body;
        return HttpResponse.json({ validated_count: 1 });
      }),
    );
    selectPara(0);
    renderWithQuery(<ParagraphDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("para-validate"));
    await waitFor(() => expect(body).toBeDefined());
    expect(body!.scope).toBe("paragraph");
    expect(body!.validated).toBe(true);
    expect(body!.paragraph_indices).toEqual([0]);
  });

  it("para-unvalidate POSTs validate-batch scope=paragraph validated=false", async () => {
    const user = userEvent.setup();
    let body: { validated: boolean } | undefined;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/validate-batch", async ({ request }) => {
        body = (await request.json()) as typeof body;
        return HttpResponse.json({ validated_count: 0 });
      }),
    );
    selectPara(0);
    renderWithQuery(<ParagraphDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("para-unvalidate"));
    await waitFor(() => expect(body).toBeDefined());
    expect(body!.validated).toBe(false);
  });
});
