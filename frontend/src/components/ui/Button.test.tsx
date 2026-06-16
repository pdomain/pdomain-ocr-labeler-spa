import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Button } from "@pdomain/pdomain-ui/primitives";

// Slice 4: local button.tsx deleted; re-pointed to pdui Button.
// Tests assert observable behaviour — element type, click handling,
// disabled behaviour, data-testid forwarding — NOT bespoke Tailwind
// class strings (now in primitives.css).

describe("Button (pdui)", () => {
  it("renders a button element", () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole("button", { name: "Click me" })).toBeInTheDocument();
  });

  it("accepts variant=primary without throwing", () => {
    render(<Button variant="primary">Primary</Button>);
    expect(screen.getByRole("button", { name: "Primary" })).toBeInTheDocument();
  });

  it("accepts variant=secondary without throwing", () => {
    render(<Button variant="secondary">Secondary</Button>);
    expect(screen.getByRole("button", { name: "Secondary" })).toBeInTheDocument();
  });

  it("accepts variant=ghost without throwing", () => {
    render(<Button variant="ghost">Ghost</Button>);
    expect(screen.getByRole("button", { name: "Ghost" })).toBeInTheDocument();
  });

  it("accepts variant=danger without throwing", () => {
    render(<Button variant="danger">Danger</Button>);
    expect(screen.getByRole("button", { name: "Danger" })).toBeInTheDocument();
  });

  it("accepts size=sm without throwing", () => {
    render(<Button size="sm">Small</Button>);
    expect(screen.getByRole("button", { name: "Small" })).toBeInTheDocument();
  });

  it("accepts size=lg without throwing", () => {
    render(<Button size="lg">Large</Button>);
    expect(screen.getByRole("button", { name: "Large" })).toBeInTheDocument();
  });

  it("accepts size=default without throwing (pdui default size)", () => {
    render(<Button size="default">Default</Button>);
    expect(screen.getByRole("button", { name: "Default" })).toBeInTheDocument();
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

  it("forwards data-testid", () => {
    render(<Button data-testid="my-btn">X</Button>);
    expect(screen.getByTestId("my-btn")).toBeInTheDocument();
  });
});
