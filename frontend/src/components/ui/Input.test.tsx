import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Input } from "@pdomain/pdomain-ui/primitives";

// Slice 2: local Input.tsx deleted; re-pointed to pdui Input.
// Tests assert observable behaviour (element type, attr forwarding, ref),
// NOT bespoke Tailwind class strings — those live in primitives.css now.

describe("Input (pdui)", () => {
  it("renders an input element", () => {
    render(<Input placeholder="test" />);
    expect(screen.getByPlaceholderText("test")).toBeInstanceOf(HTMLInputElement);
  });

  it("accepts sm size without throwing", () => {
    const { container } = render(<Input size="sm" placeholder="sm" />);
    expect(container.querySelector("input")).not.toBeNull();
  });

  it("accepts md size without throwing", () => {
    const { container } = render(<Input size="md" placeholder="md" />);
    expect(container.querySelector("input")).not.toBeNull();
  });

  it("accepts lg size without throwing (pdui superset)", () => {
    const { container } = render(<Input size="lg" placeholder="lg" />);
    expect(container.querySelector("input")).not.toBeNull();
  });

  it("forwards ref to underlying input", () => {
    const ref = { current: null as HTMLInputElement | null };
    render(<Input ref={ref} />);
    expect(ref.current).toBeInstanceOf(HTMLInputElement);
  });

  it("passes through standard HTML attributes including data-testid", () => {
    render(<Input placeholder="enter text" disabled data-testid="test-input" />);
    const input = screen.getByTestId("test-input");
    expect(input).toHaveAttribute("placeholder", "enter text");
    expect(input).toHaveAttribute("disabled");
  });

  it("merges extra className onto rendered element", () => {
    render(<Input className="my-custom" placeholder="x" />);
    const input = screen.getByPlaceholderText("x");
    expect(input.className).toContain("my-custom");
  });
});
