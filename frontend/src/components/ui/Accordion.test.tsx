// Accordion.test.tsx — pdomain-ui 0.11.0 AccordionTrigger composition tests.
//
// After migration (pdomain-ui 0.11.0 AccordionTrigger adoption):
//   AccordionItem   → pdomain-ui AccordionItem (adds .acc base class, tone prop)
//   AccordionTrigger → thin wrapper on pdui AccordionTrigger (0.11.0 generic slots)
//                      · hint → <span className="acc-hint"> inside children
//                      · keycap → endContent={<KeyCap>}
//                      · chevron: pdui default (omitted → built-in .chev span "›")
//   AccordionContent → pdomain-ui AccordionContent (.acc-body + bg-bg-sunk + px-4 pb-4)
//
// Labeler tag → pdui tone mapping:
//   tag="accent"   → .acc.accent  (via tone="accent")
//   tag="mismatch" → .acc.danger  (via tone="danger"; primitives.css uses --mismatch color)

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Accordion } from "./accordion";

describe("Accordion (pdomain-ui primitives composition)", () => {
  function SimpleAccordion({ tag }: { tag?: "accent" | "mismatch" }) {
    return (
      <Accordion type="single" collapsible>
        <Accordion.Item value="item-1" {...(tag !== undefined && { tag })}>
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
    const content = screen.queryByText("Content 1");
    if (content) {
      expect(content).not.toBeVisible();
    } else {
      expect(content).toBeNull();
    }
  });

  // AccordionItem from pdomain-ui adds .acc base class
  it("AccordionItem has primitives.css .acc base class", () => {
    const { container } = render(<SimpleAccordion />);
    const items = container.querySelectorAll("[data-state]");
    const firstItem = items[0] as HTMLElement;
    expect(firstItem.className).toContain("acc");
  });

  // tag="accent" → tone="accent" → .acc.accent in primitives.css
  it("accent tag maps to .acc.accent class via tone prop", () => {
    const { container } = render(<SimpleAccordion tag="accent" />);
    const items = container.querySelectorAll("[data-state]");
    const firstItem = items[0] as HTMLElement;
    expect(firstItem.className).toContain("accent");
  });

  // tag="mismatch" → tone="danger" → .acc.danger in primitives.css (uses --mismatch color)
  it("mismatch tag maps to .acc.danger class via tone remapping", () => {
    const { container } = render(<SimpleAccordion tag="mismatch" />);
    const items = container.querySelectorAll("[data-state]");
    const firstItem = items[0] as HTMLElement;
    expect(firstItem.className).toContain("danger");
  });

  // AccordionTrigger now uses pdui's AccordionTrigger; pdui adds .acc-trigger to the button
  it("trigger has acc-trigger class from pdomain-ui primitives.css", () => {
    const { container } = render(<SimpleAccordion />);
    const trigger = container.querySelector("button[type=button]");
    if (trigger) {
      expect(trigger.className).toContain("acc-trigger");
    }
  });

  // pdui AccordionTrigger wraps Radix button — trigger layout classes pass through via className
  it("trigger has uppercase tracking style (spec accordion label)", () => {
    const { container } = render(<SimpleAccordion />);
    const trigger = container.querySelector("button[type=button]");
    if (trigger) {
      expect(trigger.className).toContain("uppercase");
    }
  });

  it("trigger has reduced height py-2.5 (not py-4)", () => {
    const { container } = render(<SimpleAccordion />);
    const trigger = container.querySelector("button[type=button]");
    if (trigger) {
      expect(trigger.className).toContain("py-2.5");
      expect(trigger.className).not.toContain("py-4");
    }
  });

  // pdui 0.11.0: default chevron is .chev span containing "›" (not a ChevronDown SVG)
  it("trigger has pdui default .chev chevron (span with › text, no SVG)", () => {
    const { container } = render(<SimpleAccordion />);
    const chevSpan = container.querySelector(".chev");
    expect(chevSpan).toBeTruthy();
    expect(chevSpan?.textContent).toBe("›");
    // The old custom ChevronDown SVG must be absent
    const svgChevron = container.querySelector("svg");
    expect(svgChevron).toBeNull();
  });

  // AccordionContent from pdomain-ui adds .acc-body class; labeler adds bg-bg-sunk
  it("content has acc-body class from pdomain-ui", () => {
    render(<SimpleAccordion />);
    fireEvent.click(screen.getByText("Section 1"));
    const accBody = document.querySelector(".acc-body");
    expect(accBody).toBeTruthy();
  });

  it("content has bg-bg-sunk labeler-specific class", () => {
    render(<SimpleAccordion />);
    fireEvent.click(screen.getByText("Section 1"));
    const bgSunk = document.querySelector(".bg-bg-sunk");
    expect(bgSunk).toBeTruthy();
  });

  // data-testid passes through to pdui AccordionTrigger → Radix button
  it("testid prop passes through to trigger button", () => {
    render(
      <Accordion type="single" collapsible>
        <Accordion.Item value="x">
          <Accordion.Trigger data-testid="my-trigger">Label</Accordion.Trigger>
          <Accordion.Content>body</Accordion.Content>
        </Accordion.Item>
      </Accordion>,
    );
    expect(screen.getByTestId("my-trigger")).toBeInTheDocument();
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
    expect(screen.getByText("Bbox")).toBeInTheDocument();
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

  // hint uses pdui .acc-hint CSS class (muted secondary text), not bespoke Tailwind
  it("hint text has pdui .acc-hint class (not bespoke Tailwind)", () => {
    const { container } = render(
      <Accordion type="single" collapsible>
        <Accordion.Item value="x">
          <Accordion.Trigger hint="per-char styles">Char Ranges</Accordion.Trigger>
          <Accordion.Content>body</Accordion.Content>
        </Accordion.Item>
      </Accordion>,
    );
    const hintEl = Array.from(container.querySelectorAll("span")).find(
      (el) => el.textContent === "per-char styles",
    );
    expect(hintEl).toBeTruthy();
    if (hintEl) {
      expect(hintEl.className).toContain("acc-hint");
    }
  });
});
