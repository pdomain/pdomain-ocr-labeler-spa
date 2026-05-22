// useHotkey.test.tsx — unit tests for the useHotkey wrapper.
// Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md
// Issue #235
//
// Acceptance:
//   - useHotkey fires handler when key is pressed outside a form tag
//   - useHotkey does NOT fire inside form tags by default (enableOnFormTags: false)

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { useHotkey } from "./useHotkey";

// Simple test component that calls useHotkey and renders a status
function HotkeyTestComponent({
  combo,
  handler,
  enableOnFormTags,
}: {
  combo: string;
  handler: () => void;
  enableOnFormTags?: boolean;
}) {
  useHotkey(combo, handler, enableOnFormTags !== undefined ? { enableOnFormTags } : undefined);
  return <div data-testid="container">test</div>;
}

describe("useHotkey", () => {
  it("is importable and is a function", () => {
    expect(typeof useHotkey).toBe("function");
  });
});

describe("useHotkey hook", () => {
  it("renders without error", () => {
    const handler = vi.fn();
    render(<HotkeyTestComponent combo="a" handler={handler} />);
    expect(screen.getByTestId("container")).toBeInTheDocument();
  });

  it("accepts enableOnFormTags override", () => {
    const handler = vi.fn();
    // Should render without throwing
    render(<HotkeyTestComponent combo="b" handler={handler} enableOnFormTags={true} />);
    expect(screen.getByTestId("container")).toBeInTheDocument();
  });
});
