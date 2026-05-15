import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { KeyCap } from "./KeyCap";

describe("KeyCap", () => {
  it("renders single key", () => {
    render(<KeyCap keys="Ctrl" />);
    expect(screen.getByText("Ctrl")).toBeInTheDocument();
  });

  it("renders multiple keys joined by +", () => {
    render(<KeyCap keys={["Ctrl", "K"]} />);
    expect(screen.getByText("Ctrl")).toBeInTheDocument();
    expect(screen.getByText("K")).toBeInTheDocument();
  });

  it("renders + separator between multiple keys", () => {
    const { container } = render(<KeyCap keys={["Shift", "Alt", "Delete"]} />);
    const separators = container.querySelectorAll(".text-ink-3");
    expect(separators.length).toBe(2); // 3 keys = 2 separators
  });

  it("renders single key in array format", () => {
    render(<KeyCap keys={["Enter"]} />);
    expect(screen.getByText("Enter")).toBeInTheDocument();
  });

  it("applies correct styling classes", () => {
    const { container } = render(<KeyCap keys="Cmd" />);
    const cap = container.querySelector(".bg-sunk");
    expect(cap).toHaveClass("border-border-3");
    expect(cap).toHaveClass("font-mono");
  });
});
