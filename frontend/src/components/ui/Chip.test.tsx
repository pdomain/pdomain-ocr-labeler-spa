import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Chip, TriStateChip } from "@pdomain/pdomain-ui/primitives";
import type { TriStateValue } from "@pdomain/pdomain-ui/primitives";

// Slice 3: local Chip.tsx deleted; re-pointed to pdui Chip + TriStateChip.
// pdui splits local Chip (variant="static"|"tristate") into two components:
//   Chip       — static/dashed variants (HTMLSpanElement)
//   TriStateChip — tri-state cycle (HTMLDivElement)
// TristateValue (lowercase s) → TriStateValue (capital S); values identical.

describe("Chip (pdui) — data-testid forwarding", () => {
  it("forwards data-testid on TriStateChip", () => {
    render(
      <TriStateChip value="off" data-testid="my-chip" onChange={() => {}}>
        Label
      </TriStateChip>,
    );
    expect(screen.getByTestId("my-chip")).toBeInTheDocument();
    expect(screen.getByTestId("my-chip")).toHaveAttribute("data-tristate-value", "off");
  });

  it("forwards data-testid on static Chip", () => {
    render(
      <Chip variant="static" data-testid="static-chip">
        Badge
      </Chip>,
    );
    expect(screen.getByTestId("static-chip")).toBeInTheDocument();
  });
});

describe("Chip (pdui) — static variant", () => {
  it("renders children", () => {
    render(<Chip variant="static">Exact</Chip>);
    expect(screen.getByText("Exact")).toBeInTheDocument();
  });
});

describe("TriStateChip (pdui) — a11y (aria-pressed)", () => {
  it('exposes aria-pressed=false when value is "off"', () => {
    render(
      <TriStateChip value="off" onChange={() => {}}>
        Status
      </TriStateChip>,
    );
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "false");
  });

  it('exposes aria-pressed=true when value is "on"', () => {
    render(
      <TriStateChip value="on" onChange={() => {}}>
        Status
      </TriStateChip>,
    );
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "true");
  });

  it('exposes aria-pressed=mixed when value is "mixed"', () => {
    render(
      <TriStateChip value="mixed" onChange={() => {}}>
        Status
      </TriStateChip>,
    );
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "mixed");
  });
});

describe("TriStateChip (pdui) — cycle", () => {
  it("cycles from off to on on click", () => {
    const onChange = vi.fn<(v: TriStateValue) => void>();
    render(
      <TriStateChip value="off" onChange={onChange}>
        Status
      </TriStateChip>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(onChange).toHaveBeenCalledWith("on");
  });

  it("cycles from on to mixed", () => {
    const onChange = vi.fn<(v: TriStateValue) => void>();
    render(
      <TriStateChip value="on" onChange={onChange}>
        Status
      </TriStateChip>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(onChange).toHaveBeenCalledWith("mixed");
  });

  it("cycles from mixed to off", () => {
    const onChange = vi.fn<(v: TriStateValue) => void>();
    render(
      <TriStateChip value="mixed" onChange={onChange}>
        Status
      </TriStateChip>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(onChange).toHaveBeenCalledWith("off");
  });
});

describe("TriStateChip (pdui) — data-tristate attrs", () => {
  it("emits data-tristate and data-tristate-value attributes", () => {
    render(
      <TriStateChip value="on" data-testid="tsc" onChange={() => {}}>
        X
      </TriStateChip>,
    );
    const el = screen.getByTestId("tsc");
    expect(el).toHaveAttribute("data-tristate");
    expect(el).toHaveAttribute("data-tristate-value", "on");
  });
});
