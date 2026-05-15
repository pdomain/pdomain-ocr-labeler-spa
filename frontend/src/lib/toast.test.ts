// toast.test.ts — unit tests for toast wrapper.
//
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 26
// Issue: (TBD)
//
// Acceptance:
//   - Each toast level calls sonner.toast with correct border color
//   - Colors map to token names (--status-ocr, --status-exact, etc.)

import { describe, it, expect, vi } from "vitest";
import * as sonner from "sonner";
import { toast } from "./toast";

// Mock sonner.toast
vi.mock("sonner", () => ({
  toast: vi.fn(),
}));

describe("toast", () => {
  const mockSonnerToast = sonner.toast as unknown as ReturnType<typeof vi.fn>;

  it("info() calls sonner.toast with --status-ocr border", () => {
    mockSonnerToast.mockClear();
    toast.info("Test info");
    expect(mockSonnerToast).toHaveBeenCalledWith(
      "Test info",
      expect.objectContaining({
        style: expect.objectContaining({
          borderLeft: "3px solid var(--status-ocr)",
        }),
      }),
    );
  });

  it("success() calls sonner.toast with --status-exact border", () => {
    mockSonnerToast.mockClear();
    toast.success("Test success");
    expect(mockSonnerToast).toHaveBeenCalledWith(
      "Test success",
      expect.objectContaining({
        style: expect.objectContaining({
          borderLeft: "3px solid var(--status-exact)",
        }),
      }),
    );
  });

  it("warn() calls sonner.toast with --status-fuzzy border", () => {
    mockSonnerToast.mockClear();
    toast.warn("Test warn");
    expect(mockSonnerToast).toHaveBeenCalledWith(
      "Test warn",
      expect.objectContaining({
        style: expect.objectContaining({
          borderLeft: "3px solid var(--status-fuzzy)",
        }),
      }),
    );
  });

  it("error() calls sonner.toast with --status-mismatch border", () => {
    mockSonnerToast.mockClear();
    toast.error("Test error");
    expect(mockSonnerToast).toHaveBeenCalledWith(
      "Test error",
      expect.objectContaining({
        style: expect.objectContaining({
          borderLeft: "3px solid var(--status-mismatch)",
        }),
      }),
    );
  });

  it("passes through ToastOptions like id", () => {
    mockSonnerToast.mockClear();
    toast.success("Test with id", { id: "unique-123" });
    expect(mockSonnerToast).toHaveBeenCalledWith(
      "Test with id",
      expect.objectContaining({
        id: "unique-123",
        style: expect.objectContaining({
          borderLeft: "3px solid var(--status-exact)",
        }),
      }),
    );
  });
});
