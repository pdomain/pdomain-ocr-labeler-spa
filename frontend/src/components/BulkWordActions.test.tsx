// BulkWordActions.test.tsx — Lane D / Task D3.
// Page-scope validate-all / unvalidate-all + multi-select word delete +
// multi-select apply style / component.
// Q-B2 vocab fix: component and style lists sourced from useLabelVocabulary().

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { BulkWordActions } from "./BulkWordActions";
import { clearSelection, selectionStore } from "../stores/selection-store";

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderWithQuery(ui: React.ReactElement) {
  const qc = makeQueryClient();
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

function selectWords(pairs: [number, number][]) {
  selectionStore.setState((s) => ({
    ...s,
    selectedWords: pairs,
    level: "word",
    path: { lineId: pairs[0][0], wordId: pairs[0] },
  }));
}

describe("BulkWordActions (Lane D / D3)", () => {
  beforeEach(() => {
    clearSelection();
  });

  it("renders page validate-all / unvalidate-all controls", () => {
    renderWithQuery(<BulkWordActions projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("page-validate-all")).toBeInTheDocument();
    expect(screen.getByTestId("page-unvalidate-all")).toBeInTheDocument();
  });

  it("page-validate-all POSTs validate-batch scope=page validated=true", async () => {
    const user = userEvent.setup();
    let body: { scope: string; validated: boolean } | undefined;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/validate-batch", async ({ request }) => {
        body = (await request.json()) as typeof body;
        return HttpResponse.json({ validated_count: 1 });
      }),
    );
    renderWithQuery(<BulkWordActions projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("page-validate-all"));
    await waitFor(() => expect(body).toBeDefined());
    expect(body!.scope).toBe("page");
    expect(body!.validated).toBe(true);
  });

  it("page-unvalidate-all POSTs validate-batch scope=page validated=false", async () => {
    const user = userEvent.setup();
    let body: { validated: boolean } | undefined;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/validate-batch", async ({ request }) => {
        body = (await request.json()) as typeof body;
        return HttpResponse.json({ validated_count: 0 });
      }),
    );
    renderWithQuery(<BulkWordActions projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("page-unvalidate-all"));
    await waitFor(() => expect(body).toBeDefined());
    expect(body!.validated).toBe(false);
  });

  it("hides multi-select word controls when no words selected", () => {
    renderWithQuery(<BulkWordActions projectId="p1" pageIndex={0} />);
    expect(screen.queryByTestId("bulk-word-delete")).not.toBeInTheDocument();
  });

  it("shows multi-select word controls when words selected", () => {
    selectWords([
      [0, 0],
      [0, 1],
    ]);
    renderWithQuery(<BulkWordActions projectId="p1" pageIndex={0} />);
    expect(screen.getByTestId("bulk-word-delete")).toBeInTheDocument();
    expect(screen.getByTestId("bulk-word-style-select")).toBeInTheDocument();
    expect(screen.getByTestId("bulk-word-style-apply")).toBeInTheDocument();
    expect(screen.getByTestId("bulk-word-component-select")).toBeInTheDocument();
    expect(screen.getByTestId("bulk-word-component-apply")).toBeInTheDocument();
  });

  it("bulk-word-delete POSTs words/delete-batch with selected word_indices", async () => {
    const user = userEvent.setup();
    let body: { word_indices: [number, number][] } | undefined;
    server.use(
      http.post("/api/projects/:pid/pages/:idx/words/delete-batch", async ({ request }) => {
        body = (await request.json()) as typeof body;
        return HttpResponse.json({ project_id: "p1", page_index: 0, line_matches: [] });
      }),
    );
    selectWords([
      [0, 0],
      [1, 2],
    ]);
    renderWithQuery(<BulkWordActions projectId="p1" pageIndex={0} />);
    await user.click(screen.getByTestId("bulk-word-delete"));
    await waitFor(() => expect(body).toBeDefined());
    expect(body!.word_indices).toEqual([
      [0, 0],
      [1, 2],
    ]);
  });

  it("bulk-word-style-apply POSTs style per selected word", async () => {
    const user = userEvent.setup();
    const hits: string[] = [];
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/words/:li/:wi/style",
        async ({ params, request }) => {
          const b = (await request.json()) as { style: string };
          hits.push(`${params.li as string}/${params.wi as string}:${b.style}`);
          return HttpResponse.json({ project_id: "p1", page_index: 0, line_matches: [] });
        },
      ),
    );
    selectWords([
      [0, 0],
      [0, 1],
    ]);
    renderWithQuery(<BulkWordActions projectId="p1" pageIndex={0} />);
    await user.selectOptions(screen.getByTestId("bulk-word-style-select"), "italics");
    await user.click(screen.getByTestId("bulk-word-style-apply"));
    await waitFor(() => expect(hits.length).toBe(2));
    expect(hits).toContain("0/0:italics");
    expect(hits).toContain("0/1:italics");
  });

  it("bulk-word-component-apply POSTs component per selected word", async () => {
    const user = userEvent.setup();
    const hits: string[] = [];
    server.use(
      http.post(
        "/api/projects/:pid/pages/:idx/words/:li/:wi/component",
        async ({ params, request }) => {
          const b = (await request.json()) as { component: string; enabled: boolean };
          hits.push(`${params.li as string}/${params.wi as string}:${b.component}:${b.enabled}`);
          return HttpResponse.json({ project_id: "p1", page_index: 0, line_matches: [] });
        },
      ),
    );
    selectWords([[2, 3]]);
    renderWithQuery(<BulkWordActions projectId="p1" pageIndex={0} />);
    await user.selectOptions(screen.getByTestId("bulk-word-component-select"), "footnote marker");
    await user.click(screen.getByTestId("bulk-word-component-apply"));
    await waitFor(() => expect(hits.length).toBe(1));
    expect(hits[0]).toBe("2/3:footnote marker:true");
  });
});

// Q-B2 vocab-sourcing tests — these assert the component and style lists come
// from the backend vocabulary (useLabelVocabulary) so the component select
// includes "drop cap unrecovered" and styles include the canonical set.
describe("BulkWordActions — canonical vocab from useLabelVocabulary (Q-B2)", () => {
  beforeEach(() => {
    clearSelection();
    // Seed words so the multi-select controls are visible.
    selectWords([[0, 0]]);
  });

  it("component select offers 'drop cap unrecovered' (canonical component missing in old hardcoded list)", async () => {
    // MSW default handler returns the canonical vocab including "drop cap unrecovered".
    renderWithQuery(<BulkWordActions projectId="p1" pageIndex={0} />);
    const select = screen.getByTestId("bulk-word-component-select");
    // Wait for vocab to resolve (query is async).
    await waitFor(() => {
      const options = Array.from((select as HTMLSelectElement).options).map((o) => o.value);
      expect(options).toContain("drop cap unrecovered");
    });
  });

  it("style select offers canonical 'italics' (not 'italic') and excludes 'regular'", async () => {
    renderWithQuery(<BulkWordActions projectId="p1" pageIndex={0} />);
    const select = screen.getByTestId("bulk-word-style-select");
    await waitFor(() => {
      const options = Array.from((select as HTMLSelectElement).options).map((o) => o.value);
      // Canonical style name.
      expect(options).toContain("italics");
      // "regular" = clear-style; should be excluded from the bulk-apply dropdown.
      expect(options).not.toContain("regular");
    });
  });

  it("component select offers all canonical components from the backend vocab", async () => {
    server.use(
      http.get("/api/label-vocabulary", () =>
        HttpResponse.json({
          text_style_labels: ["bold", "italics"],
          word_components: [
            "drop cap",
            "drop cap unrecovered",
            "footnote marker",
            "subscript",
            "superscript",
          ],
        }),
      ),
    );
    renderWithQuery(<BulkWordActions projectId="p1" pageIndex={0} />);
    const select = screen.getByTestId("bulk-word-component-select");
    await waitFor(() => {
      const options = Array.from((select as HTMLSelectElement).options).map((o) => o.value);
      expect(options).toContain("drop cap unrecovered");
      expect(options).toContain("superscript");
      expect(options).toContain("subscript");
      expect(options).toContain("footnote marker");
      expect(options).toContain("drop cap");
    });
  });
});
