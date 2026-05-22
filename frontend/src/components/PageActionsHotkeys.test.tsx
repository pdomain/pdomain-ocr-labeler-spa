// PageActionsHotkeys.test.tsx — tests for page-action hotkeys wired to callbacks.
// Spec: docs/specs/2026-05-12-hotkeys-a11y-design.md §Global hotkeys
//       docs/specs/2026-05-12-page-actions-design.md §Hotkeys
// Issue #217
//
// Acceptance:
//   - Ctrl+R fires onReloadOcr when button is enabled
//   - Ctrl+Shift+R fires onReloadOcrEdited when hasEditedImage=true
//   - E fires onExport when button is enabled
//   - Hotkeys do NOT fire when isBusy=true

import { describe, it, expect, vi } from "vitest";
import { render, fireEvent } from "@testing-library/react";
import { PageActions } from "./PageActions";

// Note: react-hotkeys-hook fires on keydown events on the document.
// In jsdom we simulate via document-level keydown events.

function pressKey(key: string, ctrlKey = false, shiftKey = false) {
  fireEvent.keyDown(document, { key, ctrlKey, shiftKey, bubbles: true });
}

describe("PageActions hotkeys (#217)", () => {
  it("Ctrl+R fires onReloadOcr when enabled", () => {
    const onReloadOcr = vi.fn();
    render(<PageActions onReloadOcr={onReloadOcr} isBusy={false} />);
    pressKey("r", true, false);
    expect(onReloadOcr).toHaveBeenCalledOnce();
  });

  it("Ctrl+Shift+R fires onReloadOcrEdited when hasEditedImage=true", () => {
    const onReloadOcrEdited = vi.fn();
    render(
      <PageActions onReloadOcrEdited={onReloadOcrEdited} hasEditedImage={true} isBusy={false} />,
    );
    pressKey("R", true, true);
    expect(onReloadOcrEdited).toHaveBeenCalledOnce();
  });

  it("E fires onExport when enabled", () => {
    const onExport = vi.fn();
    render(<PageActions onExport={onExport} isBusy={false} />);
    pressKey("e", false, false);
    expect(onExport).toHaveBeenCalledOnce();
  });

  it("Ctrl+R does NOT fire onReloadOcr when isBusy=true", () => {
    const onReloadOcr = vi.fn();
    render(<PageActions onReloadOcr={onReloadOcr} isBusy={true} />);
    pressKey("r", true, false);
    expect(onReloadOcr).not.toHaveBeenCalled();
  });

  it("Ctrl+Shift+R does NOT fire onReloadOcrEdited when hasEditedImage=false", () => {
    const onReloadOcrEdited = vi.fn();
    render(
      <PageActions onReloadOcrEdited={onReloadOcrEdited} hasEditedImage={false} isBusy={false} />,
    );
    pressKey("R", true, true);
    expect(onReloadOcrEdited).not.toHaveBeenCalled();
  });
});
