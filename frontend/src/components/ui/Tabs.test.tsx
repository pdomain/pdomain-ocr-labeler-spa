import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "./tabs";

describe("Tabs (pdomain-ui primitives composition)", () => {
  function TestTabs({ defaultValue = "a" }) {
    return (
      <Tabs defaultValue={defaultValue}>
        <TabsList>
          <TabsTrigger value="a">Tab A</TabsTrigger>
          <TabsTrigger value="b">Tab B</TabsTrigger>
        </TabsList>
        <TabsContent value="a">Content A</TabsContent>
        <TabsContent value="b">Content B</TabsContent>
      </Tabs>
    );
  }

  it("renders tabs", () => {
    render(<TestTabs />);
    expect(screen.getByText("Tab A")).toBeInTheDocument();
    expect(screen.getByText("Tab B")).toBeInTheDocument();
  });

  it("shows active content by default", () => {
    render(<TestTabs defaultValue="a" />);
    expect(screen.getByText("Content A")).toBeVisible();
  });

  it("switches content on click", async () => {
    const user = userEvent.setup();
    render(<TestTabs defaultValue="a" />);
    await user.click(screen.getByText("Tab B"));
    // Active panel switches — Content B panel is now active
    const panel = screen.getByRole("tabpanel");
    expect(panel).toHaveTextContent("Content B");
  });

  // pdomain-ui TabsList adds .tabs class (primitives.css base)
  it("TabsList has primitives.css base class 'tabs'", () => {
    render(<TestTabs />);
    const list = screen.getByRole("tablist");
    expect(list.className).toContain("tabs");
  });

  // pdomain-ui TabsTrigger adds .tab class (primitives.css active state via data-state)
  it("TabsTrigger has primitives.css base class 'tab'", () => {
    render(<TestTabs />);
    const triggerA = screen.getByText("Tab A");
    expect(triggerA.className).toContain("tab");
  });

  // data-testid props pass through
  it("data-testid prop passes through to trigger", () => {
    render(
      <Tabs defaultValue="x">
        <TabsList>
          <TabsTrigger value="x" data-testid="my-tab">
            X
          </TabsTrigger>
        </TabsList>
        <TabsContent value="x">X content</TabsContent>
      </Tabs>,
    );
    expect(document.querySelector("[data-testid='my-tab']")).toBeInTheDocument();
  });

  // pdomain-ui TabsTrigger's .tab class has active state via data-state (not border-b-2 Tailwind)
  it("active tab trigger has data-state=active", () => {
    render(<TestTabs defaultValue="a" />);
    const triggerA = screen.getByText("Tab A");
    expect(triggerA).toHaveAttribute("data-state", "active");
  });

  it("inactive tab trigger has data-state=inactive", () => {
    render(<TestTabs defaultValue="a" />);
    const triggerB = screen.getByText("Tab B");
    expect(triggerB).toHaveAttribute("data-state", "inactive");
  });

  // Badge inside tab trigger uses primitives.css .badge class for count display
  it("badge span inside trigger renders with badge class", () => {
    render(
      <Tabs defaultValue="x">
        <TabsList>
          <TabsTrigger value="x">
            Words <span className="badge">42</span>
          </TabsTrigger>
        </TabsList>
        <TabsContent value="x">content</TabsContent>
      </Tabs>,
    );
    expect(document.querySelector(".badge")).toBeInTheDocument();
    expect(document.querySelector(".badge")?.textContent).toBe("42");
  });
});
