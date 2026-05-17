// OCRConfigModal.test.tsx — tests for OCR config modal with normalize section (#261)
// Spec: docs/specs/2026-05-12-text-normalization-design.md §Toggle UI

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { OCRConfigModal } from "./OCRConfigModal";
import type { NormalizeSettings } from "./OCRConfigModal";

function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = createQueryClient();
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const defaultSettings: NormalizeSettings = {
  normalize_for_gt_matching: false,
  normalize_plaintext_tabs: false,
  normalize_profile: "ascii",
};

function renderModal(
  props: {
    open?: boolean;
    normalizeSettings?: NormalizeSettings;
    onNormalizeChange?: (s: NormalizeSettings) => void;
    onClose?: () => void;
  } = {},
) {
  const {
    open = true,
    normalizeSettings = defaultSettings,
    onNormalizeChange = vi.fn(),
    onClose = vi.fn(),
  } = props;

  return render(
    <OCRConfigModal
      open={open}
      normalizeSettings={normalizeSettings}
      onNormalizeChange={onNormalizeChange}
      onClose={onClose}
    />,
    { wrapper: Wrapper },
  );
}

beforeEach(() => {
  // Default handler: normalize is available
  server.use(http.get("/api/normalize/available", () => HttpResponse.json({ available: true })));
});

describe("OCRConfigModal — basic rendering", () => {
  it("renders nothing when closed", () => {
    render(<OCRConfigModal open={false} onClose={vi.fn()} />, { wrapper: Wrapper });
    expect(screen.queryByTestId("ocr-config-modal")).toBeNull();
  });

  it("renders modal when open", () => {
    renderModal();
    expect(screen.getByTestId("ocr-config-modal")).not.toBeNull();
  });

  it("has normalize-gt-matching-checkbox testid", () => {
    renderModal();
    expect(screen.getByTestId("normalize-gt-matching-checkbox")).not.toBeNull();
  });

  it("has normalize-plaintext-checkbox testid", () => {
    renderModal();
    expect(screen.getByTestId("normalize-plaintext-checkbox")).not.toBeNull();
  });

  it("has normalize-profile-select testid", () => {
    renderModal();
    expect(screen.getByTestId("normalize-profile-select")).not.toBeNull();
  });
});

describe("OCRConfigModal — normalize toggles (pd-book-tools available)", () => {
  it("gt-matching checkbox unchecked by default", () => {
    renderModal();
    const cb = screen.getByTestId("normalize-gt-matching-checkbox");
    expect(cb.checked).toBe(false);
  });

  it("gt-matching checkbox enabled when normalize available", async () => {
    renderModal();
    await waitFor(() => {
      const cb = screen.getByTestId("normalize-gt-matching-checkbox");
      expect(cb.disabled).toBe(false);
    });
  });

  it("plaintext checkbox enabled when normalize available", async () => {
    renderModal();
    await waitFor(() => {
      const cb = screen.getByTestId("normalize-plaintext-checkbox");
      expect(cb.disabled).toBe(false);
    });
  });

  it("calls onNormalizeChange when gt-matching toggled", async () => {
    const onNormalizeChange = vi.fn();
    renderModal({ onNormalizeChange });
    await waitFor(() => {
      expect(screen.getByTestId("normalize-gt-matching-checkbox").disabled).toBe(false);
    });
    fireEvent.click(screen.getByTestId("normalize-gt-matching-checkbox"));
    expect(onNormalizeChange).toHaveBeenCalledOnce();
    const [args] = onNormalizeChange.mock.calls[0];
    expect(args.normalize_for_gt_matching).toBe(true);
  });

  it("calls onNormalizeChange when plaintext toggled", async () => {
    const onNormalizeChange = vi.fn();
    renderModal({ onNormalizeChange });
    await waitFor(() => {
      expect(screen.getByTestId("normalize-plaintext-checkbox").disabled).toBe(false);
    });
    fireEvent.click(screen.getByTestId("normalize-plaintext-checkbox"));
    expect(onNormalizeChange).toHaveBeenCalledOnce();
    const [args] = onNormalizeChange.mock.calls[0];
    expect(args.normalize_plaintext_tabs).toBe(true);
  });

  it("profile select is always disabled (v1: ascii only)", () => {
    renderModal();
    const sel = screen.getByTestId("normalize-profile-select");
    expect(sel.disabled).toBe(true);
    expect(sel.value).toBe("ascii");
  });
});

describe("OCRConfigModal — toggles disabled when pd-book-tools absent", () => {
  beforeEach(() => {
    // Override default handler: normalize NOT available
    server.use(http.get("/api/normalize/available", () => HttpResponse.json({ available: false })));
  });

  it("gt-matching checkbox disabled when normalize unavailable", async () => {
    renderModal();
    await waitFor(() => {
      const cb = screen.getByTestId("normalize-gt-matching-checkbox");
      expect(cb.disabled).toBe(true);
    });
  });

  it("plaintext checkbox disabled when normalize unavailable", async () => {
    renderModal();
    await waitFor(() => {
      const cb = screen.getByTestId("normalize-plaintext-checkbox");
      expect(cb.disabled).toBe(true);
    });
  });

  it("unavailable message shown when normalize not available", async () => {
    renderModal();
    await waitFor(() => {
      expect(screen.getByTestId("normalize-unavailable-message")).not.toBeNull();
    });
  });
});

describe("OCRConfigModal — toggles state before query resolves", () => {
  it("checkboxes start disabled until availability confirmed", () => {
    // Before query resolves, normalizeAvailable defaults to false — checkboxes disabled
    renderModal();
    const cb = screen.getByTestId("normalize-gt-matching-checkbox");
    // Initially disabled (safe default before probe completes)
    expect(cb.disabled).toBe(true);
  });
});

describe("OCRConfigModal — close behaviour", () => {
  it("× close button calls onClose", () => {
    const onClose = vi.fn();
    renderModal({ onClose });
    fireEvent.click(screen.getByTestId("ocr-config-close-button"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("Done button calls onClose", () => {
    const onClose = vi.fn();
    renderModal({ onClose });
    fireEvent.click(screen.getByTestId("ocr-config-done-button"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("backdrop click calls onClose", () => {
    const onClose = vi.fn();
    renderModal({ onClose });
    fireEvent.click(screen.getByTestId("ocr-config-modal"));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
