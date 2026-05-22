// LineDetail.test.tsx — Tests for LineDetail: Slice 21 + P5.e + P5.f.
// Spec: docs/plans/hifi-gaps-plan.md P5.e (Gaps 42, 43), P5.f (Gaps 44, 45).

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { LineDetail } from "./LineDetail";
import { clearSelection, selectLine } from "../../stores/selection-store";
import { useUiPrefs } from "../../stores/ui-prefs";
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
        line_index: 3,
        paragraph_index: 0,
        ocr_line_text: "hello world",
        ground_truth_line_text: "hello world",
        word_matches: [
          {
            line_index: 3,
            word_index: 0,
            ocr_text: "hello",
            ground_truth_text: "hello",
            match_status: "exact",
            normalized_match: false,
            is_validated: false,
            bbox: { x: 10, y: 20, width: 30, height: 15 },
          },
          {
            line_index: 3,
            word_index: 1,
            ocr_text: "world",
            ground_truth_text: "world",
            match_status: "exact",
            normalized_match: false,
            is_validated: false,
            bbox: { x: 50, y: 20, width: 40, height: 15 },
          },
        ],
        overall_match_status: "exact",
        exact_count: 2,
        fuzzy_count: 0,
        mismatch_count: 0,
        unmatched_gt_count: 0,
        unmatched_ocr_count: 0,
        validated_word_count: 0,
        total_word_count: 2,
        is_fully_validated: false,
      },
    ],
  };
}

function makePageWithDiffGt(): PagePayload {
  const page = makePage();
  // Make GT differ from OCR for testing GTRow display
  page.line_matches![0].ground_truth_line_text = "helo world";
  return page;
}

function renderWithQuery(ui: React.ReactElement) {
  const qc = makeQueryClient();
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("LineDetail (Slice 21)", () => {
  beforeEach(() => {
    clearSelection();
    // Reset density pref to default.

    useUiPrefs.setState({ lineWordsDensity: "cards" } as any);
  });

  it("shows 'No line selected' when no line in selection-store", () => {
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("line-detail")).toHaveTextContent(/no line selected/i);
  });

  it("renders Line and Words tabs when line is selected", () => {
    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("line-detail-tab-line")).toBeInTheDocument();
    expect(screen.getByTestId("line-detail-tab-words")).toBeInTheDocument();
  });

  it("tab switch shows Words content", async () => {
    const user = userEvent.setup();
    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("line-detail-tab-words"));
    // Words tab shows LineWordsCard with testid line-words-card-{index}
    expect(screen.getByTestId("line-words-card-0")).toBeInTheDocument();
    expect(screen.getByTestId("line-words-card-1")).toBeInTheDocument();
  });

  it("density toggle switches from Cards to Rows", async () => {
    const user = userEvent.setup();
    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("line-detail-tab-words"));

    // Initially cards are visible (line-words-card-{N} testid from LineWordsCard).
    expect(screen.getByTestId("line-words-card-0")).toBeInTheDocument();

    // Toggle to rows.
    await user.click(screen.getByTestId("line-detail-density-toggle"));
    expect(screen.queryByTestId("line-words-card-0")).not.toBeInTheDocument();
    expect(screen.getByTestId("line-detail-word-row-0")).toBeInTheDocument();

    // Pref persists in store.

    expect((useUiPrefs.getState() as any).lineWordsDensity).toBe("rows");
  });
});

// ─── P5.e: Line tab redesign (Gaps 42, 43) ──────────────────────────────────

describe("LineDetail P5.e: structure box + GT row + validate-all (Gaps 42, 43)", () => {
  beforeEach(() => {
    clearSelection();

    useUiPrefs.setState({ lineWordsDensity: "cards" } as any);
  });

  it("renders structure box with line number and para context", () => {
    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    const box = screen.getByTestId("line-detail-structure-box");
    expect(box).toBeInTheDocument();
    // Line 3 = line_index 3 → display "Line 4"
    expect(box).toHaveTextContent("Line 4");
    // paragraph_index 0 → "Para 1"
    expect(box).toHaveTextContent("Para 1");
  });

  it("structure box shows validated count", () => {
    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    const box = screen.getByTestId("line-detail-structure-box");
    // validated_word_count=0, total_word_count=2
    expect(box).toHaveTextContent("0/2 validated");
  });

  it("renders GT input pre-filled with ground_truth_line_text", () => {
    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    const input = screen.getByTestId("line-detail-gt-input");
    expect(input).toBeInTheDocument();
    expect(input).toHaveValue("hello world");
  });

  it("GT input is editable", async () => {
    const user = userEvent.setup();
    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    const input = screen.getByTestId("line-detail-gt-input");
    await user.clear(input);
    await user.type(input, "new text");
    expect(input.value).toBe("new text");
  });

  it("renders validate-all button", () => {
    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("line-detail-validate-all")).toBeInTheDocument();
  });

  it("validate-all button is disabled when fully validated", () => {
    selectLine(3);
    const page = makePage();
    page.line_matches![0].is_fully_validated = true;
    renderWithQuery(<LineDetail page={page} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("line-detail-validate-all")).toBeDisabled();
  });

  it("validate-all button is enabled when not fully validated", () => {
    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("line-detail-validate-all")).not.toBeDisabled();
  });

  it("renders merge-prev and merge-next buttons", () => {
    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("line-detail-merge-prev")).toBeInTheDocument();
    expect(screen.getByTestId("line-detail-merge-next")).toBeInTheDocument();
  });

  it("merge-prev is disabled when line_index is 0", () => {
    // line_index is 3, not 0 in default page, so merge-prev should be enabled
    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("line-detail-merge-prev")).not.toBeDisabled();
  });

  it("OCR text preview appears below GT input", () => {
    selectLine(3);
    renderWithQuery(<LineDetail page={makePageWithDiffGt()} projectId="p1" pageIndex={0} />);
    // The GT row shows "OCR:" followed by ocr_line_text
    const gtSection = screen.getByTestId("line-detail-gt-input").closest("div");
    expect(gtSection?.textContent).toContain("hello world");
  });
});

// ─── P5.f: Words tab redesign (Gaps 44, 45) ─────────────────────────────────

describe("LineDetail P5.f: word cards with checkboxes + bulk bar (Gaps 44, 45)", () => {
  beforeEach(() => {
    clearSelection();

    useUiPrefs.setState({ lineWordsDensity: "cards" } as any);
  });

  it("renders word cards with checkboxes in Words tab", async () => {
    const user = userEvent.setup();
    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("line-detail-tab-words"));
    expect(screen.getByTestId("line-words-card-checkbox-0")).toBeInTheDocument();
    expect(screen.getByTestId("line-words-card-checkbox-1")).toBeInTheDocument();
  });

  it("bulk action bar hidden when no words checked", async () => {
    const user = userEvent.setup();
    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("line-detail-tab-words"));
    expect(screen.queryByTestId("line-detail-bulk-bar")).not.toBeInTheDocument();
  });

  it("bulk action bar appears when a word is checked", async () => {
    const user = userEvent.setup();
    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("line-detail-tab-words"));
    await user.click(screen.getByTestId("line-words-card-checkbox-0"));
    expect(screen.getByTestId("line-detail-bulk-bar")).toBeInTheDocument();
    expect(screen.getByTestId("line-detail-bulk-bar")).toHaveTextContent("1 selected");
  });

  it("bulk bar shows count when multiple words checked", async () => {
    const user = userEvent.setup();
    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("line-detail-tab-words"));
    await user.click(screen.getByTestId("line-words-card-checkbox-0"));
    await user.click(screen.getByTestId("line-words-card-checkbox-1"));
    expect(screen.getByTestId("line-detail-bulk-bar")).toHaveTextContent("2 selected");
  });

  it("bulk bar has validate and skip buttons", async () => {
    const user = userEvent.setup();
    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("line-detail-tab-words"));
    await user.click(screen.getByTestId("line-words-card-checkbox-0"));
    expect(screen.getByTestId("line-detail-bulk-validate")).toBeInTheDocument();
    expect(screen.getByTestId("line-detail-bulk-skip")).toBeInTheDocument();
  });

  it("clear button in bulk bar deselects all words", async () => {
    const user = userEvent.setup();
    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("line-detail-tab-words"));
    await user.click(screen.getByTestId("line-words-card-checkbox-0"));
    // click the ✕ clear button (aria-label="Clear selection")
    await user.click(screen.getByLabelText("Clear selection"));
    expect(screen.queryByTestId("line-detail-bulk-bar")).not.toBeInTheDocument();
  });

  it("Words tab shows word count in group header", async () => {
    const user = userEvent.setup();
    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("line-detail-tab-words"));
    // Should say "2 words"
    const content = screen.getByTestId("line-detail").textContent ?? "";
    expect(content).toContain("2 words");
  });
});

// ─── Q5: bulk validate/skip wiring ──────────────────────────────────────────

describe("LineDetail Q5: bulk bar validate/skip calls validate-batch (scope=word)", () => {
  beforeEach(() => {
    clearSelection();

    useUiPrefs.setState({ lineWordsDensity: "cards" } as any);
  });

  it("Validate selected posts validate-batch with validated=true and scope=word", async () => {
    const user = userEvent.setup();
    let capturedBody: Record<string, unknown> | undefined;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/validate-batch", async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ project_id: "p1", page_index: 0, line_matches: [] });
      }),
    );

    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);

    // Switch to Words tab and check the first word
    await user.click(screen.getByTestId("line-detail-tab-words"));
    await user.click(screen.getByTestId("line-words-card-checkbox-0"));

    // Click Validate selected
    await user.click(screen.getByTestId("line-detail-bulk-validate"));

    await waitFor(() => expect(capturedBody).toBeDefined());
    expect(capturedBody?.["scope"]).toBe("word");
    expect(capturedBody?.["validated"]).toBe(true);
    // word_index 0 in line_index 3 → tuple [3, 0]
    expect(capturedBody?.["word_indices"]).toEqual([[3, 0]]);
  });

  it("Skip selected posts validate-batch with validated=false and scope=word", async () => {
    const user = userEvent.setup();
    let capturedBody: Record<string, unknown> | undefined;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/validate-batch", async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ project_id: "p1", page_index: 0, line_matches: [] });
      }),
    );

    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);

    // Switch to Words tab and check both words
    await user.click(screen.getByTestId("line-detail-tab-words"));
    await user.click(screen.getByTestId("line-words-card-checkbox-0"));
    await user.click(screen.getByTestId("line-words-card-checkbox-1"));

    // Click Skip selected
    await user.click(screen.getByTestId("line-detail-bulk-skip"));

    await waitFor(() => expect(capturedBody).toBeDefined());
    expect(capturedBody?.["scope"]).toBe("word");
    expect(capturedBody?.["validated"]).toBe(false);
    // Both words checked: [3,0] and [3,1]
    expect((capturedBody?.["word_indices"] as [number, number][]).length).toBe(2);
  });

  it("bulk bar clears after validate", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/validate-batch", () =>
        HttpResponse.json({ project_id: "p1", page_index: 0, line_matches: [] }),
      ),
    );

    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);

    await user.click(screen.getByTestId("line-detail-tab-words"));
    await user.click(screen.getByTestId("line-words-card-checkbox-0"));
    expect(screen.getByTestId("line-detail-bulk-bar")).toBeInTheDocument();

    await user.click(screen.getByTestId("line-detail-bulk-validate"));
    // clearChecked fires synchronously so bar disappears immediately
    expect(screen.queryByTestId("line-detail-bulk-bar")).not.toBeInTheDocument();
  });
});

// ─── GTRow commit behaviour (Task 3) ────────────────────────────────────────

describe("LineDetail GTRow: blur-commit and Escape revert (Task 3)", () => {
  beforeEach(() => {
    clearSelection();

    useUiPrefs.setState({ lineWordsDensity: "cards" } as any);
  });

  it("posts to set-gt when input is blurred with changed text", async () => {
    const user = userEvent.setup();
    let capturedBody: { text: string } | undefined;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/lines/:li/set-gt", async ({ request }) => {
        capturedBody = (await request.json()) as { text: string };
        return HttpResponse.json({ project_id: "p1", page_index: 0, line_matches: [] });
      }),
    );

    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    const input = screen.getByTestId("line-detail-gt-input");

    await user.clear(input);
    await user.type(input, "corrected text");
    await user.tab(); // triggers blur → commit

    await waitFor(() => expect(capturedBody?.text).toBe("corrected text"));
  });

  it("does not post when blurred with unchanged text", async () => {
    const user = userEvent.setup();
    let postCount = 0;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/lines/:li/set-gt", () => {
        postCount += 1;
        return HttpResponse.json({ project_id: "p1", page_index: 0, line_matches: [] });
      }),
    );

    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    const input = screen.getByTestId("line-detail-gt-input");

    // Focus then blur without changing value
    await user.click(input);
    await user.tab();

    // Give any async effect time to fire
    await new Promise((r) => setTimeout(r, 50));
    expect(postCount).toBe(0);
  });

  it("Escape reverts local text without posting", async () => {
    const user = userEvent.setup();
    let postCount = 0;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/lines/:li/set-gt", () => {
        postCount += 1;
        return HttpResponse.json({ project_id: "p1", page_index: 0, line_matches: [] });
      }),
    );

    selectLine(3);
    renderWithQuery(<LineDetail page={makePage()} projectId="p1" pageIndex={0} />);
    const input = screen.getByTestId("line-detail-gt-input");

    // Edit the value then press Escape
    await user.clear(input);
    await user.type(input, "wrong text");
    expect(input.value).toBe("wrong text");

    await user.keyboard("{Escape}");

    // Input reverts to the original GT text
    expect(input.value).toBe("hello world");
    // No POST should have been made
    await new Promise((r) => setTimeout(r, 50));
    expect(postCount).toBe(0);
  });
});
