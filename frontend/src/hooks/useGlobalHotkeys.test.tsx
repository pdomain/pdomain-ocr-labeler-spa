// useGlobalHotkeys.test.tsx — tests for global hotkeys hook.
// Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md §Global
// Issue #236
//
// Acceptance:
//   - Mod+S fires onSavePage immediately (non-destructive)
//   - Mod+Shift+S fires onSaveProject immediately (non-destructive)
//   - Mod+L fires onLoadPage (destructive — confirm required by caller)
//   - Mod+G fires onRematchGt (destructive — confirm required by caller)
//   - Callbacks not fired when disabled=true
//   - Hook exports correct interface
//
// Note: arrow-key combos (Mod+ArrowLeft/Right/Home/End) rely on keyCode
// mapping in hotkeys-js which doesn't fire reliably via fireEvent.keyDown
// in jsdom. Those combos are covered by E2E tests (#242).

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useGlobalHotkeys, type GlobalHotkeyHandlers } from "./useGlobalHotkeys";

function TestComponent(props: GlobalHotkeyHandlers & { disabled?: boolean }) {
  useGlobalHotkeys(props);
  return <div data-testid="container">test</div>;
}

function pressKey(key: string, ctrlKey = false, shiftKey = false) {
  fireEvent.keyDown(document, { key, ctrlKey, shiftKey, bubbles: true });
}

describe("useGlobalHotkeys (#236)", () => {
  it("is importable and is a function", () => {
    expect(typeof useGlobalHotkeys).toBe("function");
  });

  it("container renders without error", () => {
    render(<TestComponent />);
    expect(screen.getByTestId("container")).toBeInTheDocument();
  });

  it("Ctrl+S fires onSavePage", () => {
    const onSavePage = vi.fn();
    render(<TestComponent onSavePage={onSavePage} />);
    pressKey("s", true, false);
    expect(onSavePage).toHaveBeenCalledOnce();
  });

  it("Ctrl+Shift+S fires onSaveProject", () => {
    const onSaveProject = vi.fn();
    render(<TestComponent onSaveProject={onSaveProject} />);
    pressKey("S", true, true);
    expect(onSaveProject).toHaveBeenCalledOnce();
  });

  it("Ctrl+L fires onLoadPage", () => {
    const onLoadPage = vi.fn();
    render(<TestComponent onLoadPage={onLoadPage} />);
    pressKey("l", true, false);
    expect(onLoadPage).toHaveBeenCalledOnce();
  });

  it("Ctrl+G fires onRematchGt", () => {
    const onRematchGt = vi.fn();
    render(<TestComponent onRematchGt={onRematchGt} />);
    pressKey("g", true, false);
    expect(onRematchGt).toHaveBeenCalledOnce();
  });

  it("does not fire onSavePage when disabled=true", () => {
    const onSavePage = vi.fn();
    render(<TestComponent onSavePage={onSavePage} disabled={true} />);
    pressKey("s", true, false);
    expect(onSavePage).not.toHaveBeenCalled();
  });

  it("does not fire onLoadPage when disabled=true", () => {
    const onLoadPage = vi.fn();
    render(<TestComponent onLoadPage={onLoadPage} disabled={true} />);
    pressKey("l", true, false);
    expect(onLoadPage).not.toHaveBeenCalled();
  });

  it("exports GlobalHotkeyHandlers type", () => {
    // Type-level test: ensure all optional handlers compile
    const handlers: GlobalHotkeyHandlers = {
      onSavePage: vi.fn(),
      onSaveProject: vi.fn(),
      onLoadPage: vi.fn(),
      onRematchGt: vi.fn(),
      onExport: vi.fn(),
      onPrevPage: vi.fn(),
      onNextPage: vi.fn(),
      onFirstPage: vi.fn(),
      onLastPage: vi.fn(),
      disabled: false,
    };
    render(<TestComponent {...handlers} />);
    expect(screen.getByTestId("container")).toBeInTheDocument();
  });
});

// ─── H-C: Mod+Z / Mod+Shift+Z page undo/redo ─────────────────────────────────
// Spec: docs/specs/2026-06-12-event-store-undo.md (U-1, U-2, U-10).

describe("useGlobalHotkeys: undo/redo (event-store undo H-C)", () => {
  it("Ctrl+Z fires onUndo", () => {
    const onUndo = vi.fn();
    render(<TestComponent onUndo={onUndo} />);
    pressKey("z", true, false);
    expect(onUndo).toHaveBeenCalledOnce();
  });

  it("Ctrl+Shift+Z fires onRedo (not onUndo)", () => {
    const onUndo = vi.fn();
    const onRedo = vi.fn();
    render(<TestComponent onUndo={onUndo} onRedo={onRedo} />);
    pressKey("Z", true, true);
    expect(onRedo).toHaveBeenCalledOnce();
    expect(onUndo).not.toHaveBeenCalled();
  });

  it("does not fire onUndo when disabled=true", () => {
    const onUndo = vi.fn();
    render(<TestComponent onUndo={onUndo} disabled={true} />);
    pressKey("z", true, false);
    expect(onUndo).not.toHaveBeenCalled();
  });

  it("U-10: Ctrl+Z inside a text input does NOT fire page undo (native undo wins)", () => {
    const onUndo = vi.fn();
    render(
      <>
        <TestComponent onUndo={onUndo} />
        <input data-testid="gt-input" defaultValue="abc" />
      </>,
    );
    const input = screen.getByTestId("gt-input");
    input.focus();
    fireEvent.keyDown(input, { key: "z", ctrlKey: true, bubbles: true });
    expect(onUndo).not.toHaveBeenCalled();
  });

  it("U-10: Ctrl+Z inside a textarea does NOT fire page undo", () => {
    const onUndo = vi.fn();
    render(
      <>
        <TestComponent onUndo={onUndo} />
        <textarea data-testid="gt-textarea" defaultValue="abc" />
      </>,
    );
    const ta = screen.getByTestId("gt-textarea");
    ta.focus();
    fireEvent.keyDown(ta, { key: "z", ctrlKey: true, bubbles: true });
    expect(onUndo).not.toHaveBeenCalled();
  });
});
