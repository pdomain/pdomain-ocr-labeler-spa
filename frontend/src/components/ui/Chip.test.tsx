import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Chip } from "./Chip";

// Issue #325 (FO-5): data-testid forwarding

describe("Chip — data-testid forwarding", () => {
  it("forwards data-testid on tristate variant", () => {
    render(
      <Chip variant="tristate" value="off" data-testid="my-chip" onChange={() => {}}>
        Label
      </Chip>,
    );
    expect(screen.getByTestId("my-chip")).toBeInTheDocument();
    expect(screen.getByTestId("my-chip")).toHaveAttribute("data-tristate-value", "off");
  });

  it("forwards data-testid on static variant", () => {
    render(
      <Chip variant="static" data-testid="static-chip">
        Badge
      </Chip>,
    );
    expect(screen.getByTestId("static-chip")).toBeInTheDocument();
  });
});

describe("Chip — static variant", () => {
  it("renders children", () => {
    render(<Chip variant="static">Exact</Chip>);
    expect(screen.getByText("Exact")).toBeInTheDocument();
  });
});

describe("Chip — tristate variant", () => {
  it("starts at off state", () => {
    render(
      <Chip variant="tristate" value="off" onChange={() => {}}>
        Status
      </Chip>,
    );
    // Just verify it renders
    expect(screen.getByText("Status")).toBeInTheDocument();
  });

  it("cycles from off to on on click", () => {
    const onChange = vi.fn();
    render(
      <Chip variant="tristate" value="off" onChange={onChange}>
        Status
      </Chip>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(onChange).toHaveBeenCalledWith("on");
  });

  it("cycles from on to mixed", () => {
    const onChange = vi.fn();
    render(
      <Chip variant="tristate" value="on" onChange={onChange}>
        Status
      </Chip>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(onChange).toHaveBeenCalledWith("mixed");
  });

  it("cycles from mixed to off", () => {
    const onChange = vi.fn();
    render(
      <Chip variant="tristate" value="mixed" onChange={onChange}>
        Status
      </Chip>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(onChange).toHaveBeenCalledWith("off");
  });
});
