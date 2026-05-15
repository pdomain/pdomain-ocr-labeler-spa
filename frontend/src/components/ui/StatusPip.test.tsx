import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { StatusPip } from "./StatusPip";

describe("StatusPip", () => {
  it("renders without label (dot only)", () => {
    const { container } = render(<StatusPip status="exact" />);
    expect(container.querySelector(".bg-status-exact\\/10")).toBeTruthy();
  });

  it("renders with label", () => {
    render(<StatusPip status="fuzzy" label="Fuzzy" />);
    expect(screen.getByText("Fuzzy")).toBeInTheDocument();
  });

  it("mismatch applies mismatch classes", () => {
    const { container } = render(<StatusPip status="mismatch" />);
    expect(container.firstChild).toHaveClass("bg-status-mismatch/10");
  });

  it("exact status dot renders", () => {
    const { container } = render(<StatusPip status="exact" />);
    const pip = container.querySelector(".bg-status-exact");
    expect(pip).toBeTruthy();
  });

  it("fuzzy status with label", () => {
    const { container } = render(<StatusPip status="fuzzy" label="Match" />);
    expect(container.firstChild).toHaveClass("bg-status-fuzzy/10");
    expect(screen.getByText("Match")).toBeInTheDocument();
  });
});
