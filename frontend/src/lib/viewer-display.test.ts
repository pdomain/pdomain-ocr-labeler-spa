import { describe, expect, it } from "vitest";

import type { ViewerCommand } from "../api/automation";
import { displayedViewerCommand } from "./viewer-display";

const sourceCommand: ViewerCommand = {
  viewer_id: "viewer-1",
  command_seq: 8,
  project_id: "Poems00986",
  page_index: 0,
  panel: "source_alignment",
  selection: {
    word_ids: [],
    region_id: null,
    proposal_id: null,
    alignment_group_id: "group-86",
    alignment_id: "result-86",
  },
};

describe("displayedViewerCommand", () => {
  it("keeps an acknowledged source-alignment panel selected after pending work clears", () => {
    expect(displayedViewerCommand(null, sourceCommand)).toBe(sourceCommand);
  });

  it("switches the visible panel to a newer pending command", () => {
    const next = { ...sourceCommand, command_seq: 9, panel: "closed" as const };

    expect(displayedViewerCommand(next, sourceCommand)).toBe(next);
  });
});
