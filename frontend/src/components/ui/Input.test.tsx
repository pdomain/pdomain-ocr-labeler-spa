import { render } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Input } from "./Input";

describe("Input", () => {
  it("renders md size by default", () => {
    const { container } = render(<Input placeholder="test" />);
    expect(container.firstChild).toHaveClass("h-[30px]");
  });

  it("renders sm size", () => {
    const { container } = render(<Input size="sm" placeholder="test" />);
    expect(container.firstChild).toHaveClass("h-[26px]");
  });

  it("forwards ref", () => {
    const ref = { current: null as HTMLInputElement | null };
    render(<Input ref={ref} />);
    expect(ref.current).toBeInstanceOf(HTMLInputElement);
  });

  it("applies base classes", () => {
    const { container } = render(<Input placeholder="test" />);
    const input = container.firstChild as HTMLInputElement;
    expect(input).toHaveClass("bg-sunk");
    expect(input).toHaveClass("border-border-2");
    expect(input).toHaveClass("rounded-[5px]");
    expect(input).toHaveClass("text-ink-1");
  });

  it("combines custom className with size and base classes", () => {
    const { container } = render(<Input size="md" className="custom-class" placeholder="test" />);
    const input = container.firstChild as HTMLInputElement;
    expect(input).toHaveClass("custom-class");
    expect(input).toHaveClass("h-[30px]");
    expect(input).toHaveClass("bg-sunk");
  });

  it("passes through standard HTML attributes", () => {
    const { container } = render(
      <Input placeholder="enter text" disabled data-testid="test-input" />,
    );
    const input = container.firstChild as HTMLInputElement;
    expect(input).toHaveAttribute("placeholder", "enter text");
    expect(input).toHaveAttribute("disabled");
    expect(input).toHaveAttribute("data-testid", "test-input");
  });
});
