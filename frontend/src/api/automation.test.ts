import { describe, expect, it } from "vitest";

import { parseAutomationEvent, parseViewerState } from "./automation";

describe("automation DTO runtime validation", () => {
  it("accepts the frozen viewer command additions", () => {
    const state = parseViewerState({
      viewer_id: "tab-1",
      connected: true,
      desired: {
        viewer_id: "tab-1",
        command_seq: 3,
        project_id: "book-1",
        page_index: 4,
        panel: "source_alignment",
        selection: {
          word_ids: ["word-1"],
          region_id: null,
          proposal_id: null,
          alignment_group_id: "group-1",
          alignment_id: "alignment-1",
        },
      },
      acknowledged: null,
      pending: true,
      last_observation: null,
    });

    expect(state.desired?.selection.alignment_group_id).toBe("group-1");
    expect(state.desired?.panel).toBe("source_alignment");
  });

  it("rejects an event with an unknown kind", () => {
    expect(() =>
      parseAutomationEvent({
        revision: 4,
        kind: "unexpected",
        project_id: null,
        page_index: null,
        generation: null,
        job_id: null,
        viewer_id: null,
        command_seq: null,
      }),
    ).toThrow("automation event kind");
  });

  it("accepts an absent generation-reset marker from an older server as false", () => {
    const event = parseAutomationEvent({
      revision: 4,
      kind: "page_changed",
      project_id: "book-1",
      page_index: 0,
      generation: 7,
      job_id: null,
      viewer_id: null,
      command_seq: null,
    });

    expect(event.generation_reset).toBe(false);
  });

  it("accepts an explicit page-generation reset marker and rejects a malformed one", () => {
    expect(
      parseAutomationEvent({
        revision: 4,
        kind: "page_changed",
        project_id: "book-1",
        page_index: 0,
        generation: 0,
        generation_reset: true,
        job_id: null,
        viewer_id: null,
        command_seq: null,
      }).generation_reset,
    ).toBe(true);

    expect(() =>
      parseAutomationEvent({
        revision: 4,
        kind: "page_changed",
        project_id: "book-1",
        page_index: 0,
        generation: 0,
        generation_reset: "true",
        job_id: null,
        viewer_id: null,
        command_seq: null,
      }),
    ).toThrow("generation_reset must be a boolean");
  });

  it("rejects a zero command sequence", () => {
    expect(() =>
      parseViewerState({
        viewer_id: "tab-1",
        connected: true,
        desired: {
          viewer_id: "tab-1",
          command_seq: 0,
          project_id: "book-1",
          page_index: 0,
          panel: "closed",
          selection: {
            word_ids: [],
            region_id: null,
            proposal_id: null,
            alignment_group_id: null,
            alignment_id: null,
          },
        },
        acknowledged: null,
        pending: true,
        last_observation: null,
      }),
    ).toThrow("command_seq must be a positive integer");
  });
});
