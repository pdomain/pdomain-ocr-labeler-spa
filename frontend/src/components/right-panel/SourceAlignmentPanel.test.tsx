import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { server } from "../../test/server";
import { SourceAlignmentPanel } from "./SourceAlignmentPanel";

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SourceAlignmentPanel
        projectId="Poems00986"
        pageIndex={0}
        generation={4}
        alignmentId="result-4"
        groupId="group-verse"
        onRendered={vi.fn()}
        onUnavailable={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

function InlineMarkerParent() {
  const [marker, setMarker] = useState<{ viewerId: string; commandSeq: number } | null>(null);
  return (
    <>
      <output data-testid="inline-marker">
        {marker === null ? "pending" : `${marker.viewerId}:${marker.commandSeq}`}
      </output>
      <SourceAlignmentPanel
        projectId="Poems00986"
        pageIndex={0}
        generation={4}
        alignmentId="result-4"
        groupId="group-verse"
        onRendered={() => {
          setMarker((current) => {
            if (current?.viewerId === "viewer-1" && current.commandSeq === 8) return current;
            return { viewerId: "viewer-1", commandSeq: 8 };
          });
        }}
        onUnavailable={vi.fn()}
      />
    </>
  );
}

describe("SourceAlignmentPanel", () => {
  it("defers the render acknowledgement until a matching page generation is available", async () => {
    server.use(
      http.get("/api/projects/:projectId/pages/:pageIndex/source-alignment", () =>
        HttpResponse.json({ generation: 3, stale: false, result: null }),
      ),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const onRendered = vi.fn();

    render(
      <QueryClientProvider client={client}>
        <SourceAlignmentPanel
          projectId="Poems00986"
          pageIndex={0}
          generation={4}
          alignmentId="result-4"
          groupId="group-verse"
          onRendered={onRendered}
          onUnavailable={vi.fn()}
        />
      </QueryClientProvider>,
    );

    await waitFor(() =>
      expect(client.getQueryData(["source-alignment", "Poems00986", 0])).toBeDefined(),
    );
    expect(onRendered).not.toHaveBeenCalled();

    client.setQueryData(["source-alignment", "Poems00986", 0], {
      generation: 4,
      stale: false,
      result: {
        result_id: "result-4",
        input_generation: 4,
        warnings: [],
        groups: [
          {
            group_id: "group-verse",
            f2_text: "F2",
            p3_text: "P3",
            ocr_text: "OCR",
            disposition: "accepted",
            decision: "accepted",
            note: "",
            reviewed_text: null,
            warnings: [],
          },
        ],
        layout_hints: [],
        unresolved: [],
      },
    });

    await waitFor(() => expect(onRendered).toHaveBeenCalledTimes(1));
  });

  it("renders mapped verse lines plus unresolved source evidence", async () => {
    server.use(
      http.get("/api/projects/:projectId/pages/:pageIndex/source-alignment", () =>
        HttpResponse.json({
          generation: 4,
          stale: false,
          result: {
            result_id: "result-4",
            input_generation: 4,
            warnings: ["Source page continues on the next image."],
            groups: [
              {
                group_id: "group-verse",
                f2_text: "One bright line",
                p3_text: "One bright line",
                ocr_text: "One bright line",
                disposition: "accepted",
                decision: "accepted",
                note: "",
                reviewed_text: null,
                warnings: ["Mapped through an exact anchor."],
              },
            ],
            projection: {
              layout_hints: [
                {
                  hint: {
                    kind: "verse",
                    source: "F2",
                    source_ref: "Poems00986",
                    lines: [{ text: "One bright line", stanza_index: 2, indent_hint: "hanging" }],
                  },
                  group_ids: ["group-verse"],
                  disposition: "accepted",
                },
              ],
              unresolved: [
                {
                  source_kind: "illustration",
                  source_ref: "Poems00986:12",
                  disposition: "exhausted",
                  warnings: ["No OCR anchor."],
                },
              ],
            },
          },
        }),
      ),
    );

    renderPanel();

    await waitFor(() => expect(screen.getByTestId("source-alignment-panel")).toBeInTheDocument());
    expect(screen.getAllByText("One bright line")).toHaveLength(4);
    expect(screen.getByText("Stanza 2")).toBeInTheDocument();
    expect(screen.getByText("Indent hanging")).toBeInTheDocument();
    expect(screen.getByTestId("source-alignment-group-warnings")).toHaveTextContent("exact anchor");
    expect(screen.getByTestId("source-alignment-result-warnings")).toHaveTextContent("continues");
    expect(screen.getByTestId("source-alignment-unresolved")).toHaveTextContent("exhausted");
  });

  it("settles an inline parent render marker without a render loop", async () => {
    server.use(
      http.get("/api/projects/:projectId/pages/:pageIndex/source-alignment", () =>
        HttpResponse.json({
          generation: 4,
          stale: false,
          result: {
            result_id: "result-4",
            input_generation: 4,
            warnings: [],
            groups: [
              {
                group_id: "group-verse",
                f2_text: "F2",
                p3_text: "P3",
                ocr_text: "OCR",
                disposition: "accepted",
                decision: "accepted",
                note: "",
                reviewed_text: null,
                warnings: [],
              },
            ],
            projection: { layout_hints: [], unresolved: [] },
          },
        }),
      ),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <InlineMarkerParent />
      </QueryClientProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("inline-marker")).toHaveTextContent("viewer-1:8"),
    );
    expect(screen.getByTestId("source-alignment-panel")).toBeInTheDocument();
  });
});
