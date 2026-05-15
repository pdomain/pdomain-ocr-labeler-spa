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
});
