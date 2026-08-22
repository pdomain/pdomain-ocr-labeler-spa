import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../../test/server";
import { TypographySection } from "./TypographySection";

const head = {
  project_id: "p1",
  page_index: 0,
  logical_page_id: "page",
  word_id: "w1",
  page_sha256: "1".repeat(64),
  image_sha256: "2".repeat(64),
  text_sha256: "3".repeat(64),
  page_head_sha256: "4".repeat(64),
  word_revision: 0,
  revision: 0,
  correction: null,
  head_token: "5".repeat(64),
  text: "á👨‍👩‍👧‍👦b",
  graphemes: ["á", "👨‍👩‍👧‍👦", "b"],
  grapheme_map_version: "server-graphemes-v1",
  taxonomy: {
    version: "server-taxonomy-v1",
    taxonomy_hash: "6".repeat(64),
    labels: ["italic", "bold", "small caps", "superscript", "subscript", "drop cap"].map(
      (value) => ({
        value,
        display_name: value.replace(/^./, (letter) => letter.toUpperCase()),
        required_for_completion: true,
        trainable: true,
      }),
    ),
  },
};

function renderSection() {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <TypographySection projectId="p1" pageIndex={0} wordId="w1" />
    </QueryClientProvider>,
  );
}

describe("TypographySection", () => {
  it("renders backend graphemes and creates adjacent half-open spans with multiple labels", async () => {
    let body: Record<string, unknown> | undefined;
    server.use(
      http.get("/api/projects/p1/pages/0/typography/words/w1/head", () => HttpResponse.json(head)),
      http.post("/api/projects/p1/pages/0/typography/words/w1/corrections", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...head, revision: 1 });
      }),
    );
    const user = userEvent.setup();
    renderSection();
    await screen.findByText("👨‍👩‍👧‍👦");
    expect(screen.getAllByTestId(/typography-grapheme-/)).toHaveLength(3);
    await user.click(screen.getByTestId("typography-grapheme-0"));
    await user.click(screen.getByTestId("typography-grapheme-1"));
    await user.click(screen.getByRole("button", { name: "Italic" }));
    await user.click(screen.getByRole("button", { name: "Bold" }));
    await user.click(screen.getByRole("button", { name: "Add span" }));
    await user.click(screen.getByRole("button", { name: "Save typography" }));
    await waitFor(() => expect(body).toBeDefined());
    expect(body).toMatchObject({
      taxonomy_version: "server-taxonomy-v1",
      taxonomy_hash: "6".repeat(64),
      grapheme_map_version: "server-graphemes-v1",
      replacement_word_revision: 1,
    });
    const replacement = body!.replacement as {
      spans: { start: number; end: number; label: string }[];
    };
    expect(replacement.spans.map(({ start, end, label }) => ({ start, end, label }))).toEqual([
      { start: 0, end: 2, label: "italic" },
      { start: 0, end: 2, label: "bold" },
    ]);
  });

  it("supports whole-word reviewed-regular and reports stale heads", async () => {
    server.use(
      http.get("/api/projects/p1/pages/0/typography/words/w1/head", () => HttpResponse.json(head)),
      http.post("/api/projects/p1/pages/0/typography/words/w1/corrections", () =>
        HttpResponse.json({ detail: "typography head is stale" }, { status: 409 }),
      ),
    );
    const user = userEvent.setup();
    renderSection();
    await screen.findByText("👨‍👩‍👧‍👦");
    await user.click(screen.getByRole("button", { name: "Whole word" }));
    await user.click(screen.getByRole("button", { name: "Reviewed regular" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/stale/i);
  });

  it("splits and merges adjacent grapheme spans", async () => {
    server.use(
      http.get("/api/projects/p1/pages/0/typography/words/w1/head", () => HttpResponse.json(head)),
    );
    const user = userEvent.setup();
    renderSection();
    await screen.findByText("👨‍👩‍👧‍👦");
    await user.click(screen.getByTestId("typography-grapheme-0"));
    await user.click(screen.getByTestId("typography-grapheme-2"));
    await user.click(screen.getByRole("button", { name: "Italic" }));
    await user.click(screen.getByRole("button", { name: "Add span" }));
    await user.click(screen.getByRole("button", { name: "Split span 1" }));
    expect(screen.getAllByTestId(/typography-span-/)).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: "Merge span 1" }));
    expect(screen.getAllByTestId(/typography-span-/)).toHaveLength(1);
  });

  it("shows non-stale save failures and offers no destructive pseudo-undo", async () => {
    server.use(
      http.get("/api/projects/p1/pages/0/typography/words/w1/head", () =>
        HttpResponse.json({ ...head, correction: { replacement: { spans: [] } } }),
      ),
      http.post("/api/projects/p1/pages/0/typography/words/w1/corrections", () =>
        HttpResponse.json({ detail: "invalid typography taxonomy states" }, { status: 422 }),
      ),
    );
    const user = userEvent.setup();
    renderSection();
    await screen.findByText("👨‍👩‍👧‍👦");
    expect(screen.queryByRole("button", { name: /undo/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reviewed regular" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /invalid typography taxonomy states/i,
    );
  });
});
