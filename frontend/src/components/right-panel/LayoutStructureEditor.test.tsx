import { layoutStructureFromUnknown } from "./layoutStructure";
import { type LayoutStructureDraft } from "./layoutStructure";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LayoutStructureEditor } from "./LayoutStructureEditor";

const STRUCTURE: LayoutStructureDraft = {
  kind: "poetry",
  lines: [
    {
      text: "First line",
      word_ids: ["word-a", "word-b"],
      stanza_index: 0,
      indent_hint: "2em",
      word_signatures: [],
    },
    { text: "Second line", word_ids: ["word-c"], stanza_index: 1, word_signatures: [] },
  ],
  column_group_id: "columns-1",
  column_index: 0,
  reading_order: 1,
  table_rows: [],
};

describe("LayoutStructureEditor", () => {
  it("shows readable verse and column fields and reports corrections", async () => {
    const user = userEvent.setup();
    let changed: LayoutStructureDraft | undefined;
    render(
      <LayoutStructureEditor
        structure={STRUCTURE}
        onChange={(next) => {
          changed = next;
        }}
      />,
    );

    expect(screen.getByTestId("region-layout-line-0-word-count")).toHaveTextContent("2 words");
    expect(screen.getByTestId("region-layout-line-0-stanza")).toHaveValue(0);
    expect(screen.getByTestId("region-layout-column-group")).toHaveValue("columns-1");

    await user.clear(screen.getByTestId("region-layout-line-0-stanza"));
    await user.type(screen.getByTestId("region-layout-line-0-stanza"), "2");
    await user.clear(screen.getByTestId("region-layout-line-0-indent"));
    await user.type(screen.getByTestId("region-layout-line-0-indent"), "3em");
    await user.clear(screen.getByTestId("region-layout-reading-order"));
    await user.type(screen.getByTestId("region-layout-reading-order"), "4");

    expect(changed).toEqual({
      ...STRUCTURE,
      lines: [
        {
          text: "First line",
          word_ids: ["word-a", "word-b"],
          stanza_index: 2,
          indent_hint: "3em",
          word_signatures: [],
        },
        { text: "Second line", word_ids: ["word-c"], stanza_index: 1, word_signatures: [] },
      ],
      reading_order: 4,
    });
  });

  it("does not treat malformed evidence as reviewed structure", () => {
    expect(
      layoutStructureFromUnknown({ kind: "poetry", lines: [{ text: "line", word_ids: [] }] }),
    ).toBeNull();
    expect(layoutStructureFromUnknown({ lines: "not-lines" })).toBeNull();
  });
});

it("retains column and table structure when the shared wire omits empty lines", () => {
  expect(
    layoutStructureFromUnknown({
      kind: "column_flow",
      column_group_id: "paired-columns",
      column_index: 0,
      reading_order: 1,
    }),
  ).toEqual({
    kind: "column_flow",
    column_group_id: "paired-columns",
    column_index: 0,
    reading_order: 1,
    lines: [],
    table_rows: [],
  });
  expect(
    layoutStructureFromUnknown({
      kind: "table",
      table_rows: [{ cells: [{ text: "Fruit", word_ids: ["word-1"] }] }],
    }),
  ).toEqual({
    kind: "table",
    lines: [],
    table_rows: [{ cells: [{ text: "Fruit", word_ids: ["word-1"], word_signatures: [] }] }],
  });
  expect(layoutStructureFromUnknown({ kind: "poetry" })).toBeNull();
});
