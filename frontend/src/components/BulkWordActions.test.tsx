// BulkWordActions.test.tsx — Lane D / Task D3.
// Page-scope validate-all / unvalidate-all + multi-select word delete +
// multi-select apply style / component.

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
