// WorkspaceToolbar.test.tsx — slot composition for the in-body workspace band.
//
// M1 (header → workspace-toolbar realignment, D-047): the document/page-scoped
// controls move out of the AppShell chrome header into a full-width
// StageToolbar band at the top of the project route. This test asserts the
// three-slot composition and the stable `workspace-toolbar` testid.

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { WorkspaceToolbar } from "./WorkspaceToolbar";

describe("WorkspaceToolbar — StageToolbar band (D-047)", () => {
  it("carries data-testid=workspace-toolbar when slots have content", () => {
    render(
      <WorkspaceToolbar
        leftSlot={<span data-testid="ws-left">left</span>}
        centerSlot={<span data-testid="ws-center">center</span>}
        rightSlot={<span data-testid="ws-right">right</span>}
      />,
    );
    expect(screen.getByTestId("workspace-toolbar")).toBeInTheDocument();
  });

  it("renders leftSlot / centerSlot / rightSlot content", () => {
    render(
      <WorkspaceToolbar
        leftSlot={<span data-testid="ws-left">left</span>}
        centerSlot={<span data-testid="ws-center">center</span>}
        rightSlot={<span data-testid="ws-right">right</span>}
      />,
    );
    expect(screen.getByTestId("ws-left")).toBeInTheDocument();
    expect(screen.getByTestId("ws-center")).toBeInTheDocument();
    expect(screen.getByTestId("ws-right")).toBeInTheDocument();
  });

  it("renders nothing when all slots are empty (StageToolbar WS7 contract)", () => {
    // pdomain-ui StageToolbar returns null with no slot content — an empty
    // role=toolbar with no interactive children is invalid ARIA.
    const { container } = render(<WorkspaceToolbar />);
    expect(screen.queryByTestId("workspace-toolbar")).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it("has role=toolbar for the landmark", () => {
    render(<WorkspaceToolbar leftSlot={<span data-testid="ws-left">left</span>} />);
    expect(screen.getByTestId("workspace-toolbar")).toHaveAttribute("role", "toolbar");
  });
});
