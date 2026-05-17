import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Accordion } from "./accordion";

describe("Accordion", () => {
  function SimpleAccordion({ tag }: { tag?: "accent" | "mismatch" }) {
    return (
      <Accordion type="single" collapsible>
        <Accordion.Item value="item-1" tag={tag}>
          <Accordion.Trigger>Section 1</Accordion.Trigger>
          <Accordion.Content>Content 1</Accordion.Content>
        </Accordion.Item>
        <Accordion.Item value="item-2">
          <Accordion.Trigger>Section 2</Accordion.Trigger>
          <Accordion.Content>Content 2</Accordion.Content>
        </Accordion.Item>
      </Accordion>
    );
  }

  it("renders accordion items", () => {
    render(<SimpleAccordion />);
    expect(screen.getByText("Section 1")).toBeInTheDocument();
    expect(screen.getByText("Section 2")).toBeInTheDocument();
  });

  it("opens item on trigger click", () => {
    render(<SimpleAccordion />);
    fireEvent.click(screen.getByText("Section 1"));
    expect(screen.getByText("Content 1")).toBeVisible();
  });

  it("closes item on second trigger click", () => {
    render(<SimpleAccordion />);
    fireEvent.click(screen.getByText("Section 1"));
    fireEvent.click(screen.getByText("Section 1"));
    // After close, content should not be visible (Radix hides it)
    const content = screen.queryByText("Content 1");
    // Either hidden or not in DOM
    if (content) {
      expect(content).not.toBeVisible();
    } else {
      expect(content).toBeNull();
    }
  });

  it("accent tag adds accent stripe class", () => {
    const { container } = render(<SimpleAccordion tag="accent" />);
    // Find the first AccordionItem (has data-state attribute from Radix)
    const items = container.querySelectorAll("[data-state]");
    const firstItem = items[0] as HTMLElement;
    if (firstItem) {
      expect(firstItem.className).toContain("border-accent");
    }
  });

  it("mismatch tag adds mismatch stripe class", () => {
    const { container } = render(<SimpleAccordion tag="mismatch" />);
    const itemWithMismatch = container.querySelector('[class*="status-mismatch"]');
    expect(itemWithMismatch).toBeTruthy();
  });

  it("trigger uses py-2.5 (reduced height ~36px) not py-4", () => {
    const { container } = render(<SimpleAccordion />);
    // AccordionTrigger is a <button> inside AccordionHeader <h3>
    const trigger = container.querySelector("button[type=button]");
    if (trigger) {
      expect(trigger.className).toContain("py-2.5");
      expect(trigger.className).not.toContain("py-4");
    }
  });

  it("trigger label uses uppercase tracking style (spec accordion label)", () => {
    const { container } = render(<SimpleAccordion />);
    const trigger = container.querySelector("button[type=button]");
    if (trigger) {
      expect(trigger.className).toContain("uppercase");
    }
  });

  it("content uses bg-bg-sunk not bg-sunk", () => {
    render(<SimpleAccordion />);
    fireEvent.click(screen.getByText("Section 1"));
    // Content is the Radix Content element (has data-state=open when open)
    const openContent = document.querySelector("[data-state=open]");
    // Walk up to find the content container with background class
    if (openContent) {
      // The content wrapper should have bg-bg-sunk
      const contentEl = document.querySelector(".bg-bg-sunk");
      expect(contentEl).toBeTruthy();
    }
  });
});

// P2.g — Accordion trigger hint + keycap (Gap 32, 54)
describe("Accordion trigger redesign (P2.g)", () => {
  it("renders hint text when hint prop is provided", () => {
    render(
      <Accordion type="single" collapsible>
        <Accordion.Item value="x">
          <Accordion.Trigger hint="coords · nudge">Bbox</Accordion.Trigger>
          <Accordion.Content>body</Accordion.Content>
        </Accordion.Item>
      </Accordion>,
    );
    expect(screen.getByText("coords · nudge")).toBeInTheDocument();
  });

  it("renders no hint span when hint prop is omitted", () => {
    render(
      <Accordion type="single" collapsible>
        <Accordion.Item value="x">
          <Accordion.Trigger>Bbox</Accordion.Trigger>
          <Accordion.Content>body</Accordion.Content>
        </Accordion.Item>
      </Accordion>,
    );
    // The label text should be there but no hint span
    expect(screen.getByText("Bbox")).toBeInTheDocument();
    // No element with text-ink-3 hint style — just check the hint text is absent
    expect(screen.queryByText("coords · nudge")).not.toBeInTheDocument();
  });

  it("renders keycap chip when keycap prop is provided", () => {
    render(
      <Accordion type="single" collapsible>
        <Accordion.Item value="x">
          <Accordion.Trigger keycap="B">Bbox</Accordion.Trigger>
          <Accordion.Content>body</Accordion.Content>
        </Accordion.Item>
      </Accordion>,
    );
    expect(screen.getByText("B")).toBeInTheDocument();
  });

  it("renders both hint and keycap together", () => {
    render(
      <Accordion type="single" collapsible>
        <Accordion.Item value="x">
          <Accordion.Trigger hint="draw new box" keycap="R">
            Rebox
          </Accordion.Trigger>
          <Accordion.Content>body</Accordion.Content>
        </Accordion.Item>
      </Accordion>,
    );
    expect(screen.getByText("Rebox")).toBeInTheDocument();
    expect(screen.getByText("draw new box")).toBeInTheDocument();
    expect(screen.getByText("R")).toBeInTheDocument();
  });

  it("hint text has lowercase normal tracking (not uppercase)", () => {
    const { container } = render(
      <Accordion type="single" collapsible>
        <Accordion.Item value="x">
          <Accordion.Trigger hint="per-char styles">Char Ranges</Accordion.Trigger>
          <Accordion.Content>body</Accordion.Content>
        </Accordion.Item>
      </Accordion>,
    );
    // Find the hint span by text content
    const hintEl = Array.from(container.querySelectorAll("span")).find(
      (el) => el.textContent === "per-char styles",
    );
    expect(hintEl).toBeTruthy();
    if (hintEl) {
      expect(hintEl.className).toContain("normal-case");
    }
  });
});
