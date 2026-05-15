import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Button } from "./button";

describe("Button", () => {
  it("renders with default variant and size", () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole("button", { name: "Click me" })).toBeInTheDocument();
  });

  it("primary variant has accent class", () => {
    const { container } = render(<Button variant="primary">Primary</Button>);
    expect(container.firstChild).toHaveClass("bg-accent");
  });

  it("secondary variant has raised background", () => {
    const { container } = render(<Button variant="secondary">Secondary</Button>);
    expect(container.firstChild).toHaveClass("bg-raised");
  });

  it("ghost variant starts transparent", () => {
    const { container } = render(<Button variant="ghost">Ghost</Button>);
    expect(container.firstChild).toHaveClass("bg-transparent");
  });

  it("danger variant has mismatch styling", () => {
    const { container } = render(<Button variant="danger">Danger</Button>);
    const el = container.firstChild as HTMLElement;
    expect(el.className).toContain("status-mismatch");
  });

  it("sm size has correct height class", () => {
    const { container } = render(<Button size="sm">Small</Button>);
    expect(container.firstChild).toHaveClass("h-6");
  });

  it("lg size has correct height class", () => {
    const { container } = render(<Button size="lg">Large</Button>);
    expect(container.firstChild).toHaveClass("h-[34px]");
  });

  it("default size has 30px height class", () => {
    const { container } = render(<Button size="default">Default</Button>);
    expect(container.firstChild).toHaveClass("h-[30px]");
  });

  it("click fires callback", () => {
    const handler = vi.fn();
    render(<Button onClick={handler}>Click</Button>);
    fireEvent.click(screen.getByRole("button"));
    expect(handler).toHaveBeenCalledOnce();
  });

  it("disabled button does not fire click", () => {
    const handler = vi.fn();
    render(
      <Button disabled onClick={handler}>
        Click
      </Button>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(handler).not.toHaveBeenCalled();
  });
});
