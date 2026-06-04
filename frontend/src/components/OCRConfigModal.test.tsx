// OCRConfigModal.test.tsx — tests for OCR config modal with normalize section (#261)
// Covers: B-ACTIONS-001, B-ACTIONS-016, B-ACTIONS-017, F-OCR-CONFIG-01, F-OCR-CONFIG-NORMALIZE-ROTATE-01
// Spec: docs/specs/2026-05-12-text-normalization-design.md §Toggle UI
// Issue #447: POST /api/ocr-config/auto-rotate failures must be surfaced to the user.

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

describe("OCRConfigModal — normalize toggles (pdomain-book-tools available)", () => {
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

describe("OCRConfigModal — toggles disabled when pdomain-book-tools absent", () => {
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

  // NOTE: Backdrop (overlay) click-to-dismiss is now handled natively by Radix Dialog
  // via onOpenChange → onClose. The old test fired a click on ocr-config-modal (which
  // was the backdrop wrapper div). With Radix, ocr-config-modal is on DialogContent
  // (the inner panel), so that click path is no longer the backdrop-dismiss route.
  // Radix Dialog's native Escape + overlay-click behaviour is tested in the pdomain-ui
  // primitives package and doesn't need re-testing here.
});

// ─── Lane C / Task C3: real OCR model selection (un-stub the modal) ──────────
describe("OCRConfigModal — model selection (Lane C / C3)", () => {
  const fullConfig = {
    detection_options: [
      { key: "stock", label: "Stock (bundled DocTR)", source: "stock", is_default: true },
      {
        key: "hf-latest",
        label: "Hugging Face (latest)",
        source: "huggingface",
        is_default: false,
      },
    ],
    recognition_options: [
      { key: "stock", label: "Stock (bundled DocTR)", source: "stock", is_default: true },
      {
        key: "hf-latest",
        label: "Hugging Face (latest)",
        source: "huggingface",
        is_default: false,
      },
    ],
    selected_detection: "stock",
    selected_recognition: "stock",
    hf_pinned_revision: null,
    selection_reason: "stock-fallback",
    auto_rotate_available: false,
    auto_rotate_on_load: true,
    auto_rotate_method: "auto",
  };

  beforeEach(() => {
    server.use(http.get("/api/ocr-config", () => HttpResponse.json(fullConfig)));
  });

  it("detection/recognition selects are visible and populated from GET", async () => {
    renderModal();
    const detSel = (await screen.findByTestId("ocr-detection-model-select")) as HTMLSelectElement;
    const recoSel = screen.getByTestId("ocr-recognition-model-select") as HTMLSelectElement;
    // Visible (not a display:none stub).
    expect(detSel.closest('[style*="display: none"]')).toBeNull();
    await waitFor(() => {
      expect(detSel.querySelectorAll("option").length).toBeGreaterThanOrEqual(2);
    });
    expect(recoSel.querySelectorAll("option").length).toBeGreaterThanOrEqual(2);
    // Selected value reflects the GET response.
    expect(detSel.value).toBe("stock");
    expect(recoSel.value).toBe("stock");
  });

  it("renders the HF revision input and Apply / Rescan buttons (no stub attr)", async () => {
    renderModal();
    expect(await screen.findByTestId("ocr-hf-revision-input")).not.toHaveAttribute(
      "data-testid-stub",
    );
    expect(screen.getByTestId("ocr-config-apply-button")).not.toHaveAttribute("data-testid-stub");
    expect(screen.getByTestId("ocr-rescan-models-button")).not.toHaveAttribute("data-testid-stub");
  });

  it("choosing a model + Apply POSTs /api/ocr-config/models", async () => {
    let bodySeen: unknown = null;
    const modelsSpy = vi.fn(async ({ request }: { request: Request }) => {
      bodySeen = await request.json();
      return HttpResponse.json(fullConfig);
    });
    server.use(http.post("/api/ocr-config/models", modelsSpy));

    renderModal();
    const detSel = (await screen.findByTestId("ocr-detection-model-select")) as HTMLSelectElement;
    await waitFor(() => {
      expect(detSel.querySelectorAll("option").length).toBeGreaterThanOrEqual(2);
    });
    fireEvent.change(detSel, { target: { value: "hf-latest" } });
    fireEvent.click(screen.getByTestId("ocr-config-apply-button"));

    await waitFor(() => expect(modelsSpy).toHaveBeenCalled());
    expect(bodySeen).toMatchObject({ detection_key: "hf-latest", recognition_key: "stock" });
  });

  it("Rescan POSTs /api/ocr-config/rescan", async () => {
    const rescanSpy = vi.fn(() => HttpResponse.json(fullConfig));
    server.use(http.post("/api/ocr-config/rescan", rescanSpy));

    renderModal();
    fireEvent.click(await screen.findByTestId("ocr-rescan-models-button"));
    await waitFor(() => expect(rescanSpy).toHaveBeenCalled());
  });
});

// ─── Issue #447: POST /api/ocr-config/auto-rotate HTTP failure surfacing ─────
describe("OCRConfigModal — auto-rotate POST failure surfacing (#447)", () => {
  beforeEach(() => {
    // Provide a working ocr-config GET so auto-rotate controls are rendered and enabled.
    server.use(
      http.get("/api/ocr-config", () =>
        HttpResponse.json({
          auto_rotate_available: true,
          auto_rotate_on_load: true,
          auto_rotate_method: "auto",
        }),
      ),
    );
  });

  it("shows ocr-config-save-error banner when POST returns 500, modal stays open", async () => {
    // Override POST to return a 500.
    server.use(
      http.post("/api/ocr-config/auto-rotate", () =>
        HttpResponse.json({ detail: "Internal Server Error" }, { status: 500 }),
      ),
    );

    const onClose = vi.fn();
    renderModal({ onClose });

    // Wait for auto-rotate controls to be enabled (ocr-config GET resolved).
    await waitFor(() => {
      expect(screen.getByTestId("auto-rotate-checkbox").disabled).toBe(false);
    });

    // Toggle the checkbox to trigger the POST.
    fireEvent.click(screen.getByTestId("auto-rotate-checkbox"));

    // Error banner should appear.
    await waitFor(() => {
      expect(screen.getByTestId("ocr-config-save-error")).toBeInTheDocument();
    });

    // Modal must still be open — onClose must NOT have been called.
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByTestId("ocr-config-modal")).toBeInTheDocument();
  });

  it("shows ocr-config-save-error banner when POST returns 422", async () => {
    server.use(
      http.post("/api/ocr-config/auto-rotate", () =>
        HttpResponse.json({ detail: "Unprocessable Entity" }, { status: 422 }),
      ),
    );

    renderModal();

    await waitFor(() => {
      expect(screen.getByTestId("auto-rotate-checkbox").disabled).toBe(false);
    });

    fireEvent.click(screen.getByTestId("auto-rotate-checkbox"));

    await waitFor(() => {
      expect(screen.getByTestId("ocr-config-save-error")).toBeInTheDocument();
    });
  });

  it("clears error banner on a subsequent successful POST", async () => {
    // First POST fails.
    server.use(
      http.post("/api/ocr-config/auto-rotate", () =>
        HttpResponse.json({ detail: "error" }, { status: 500 }),
      ),
    );

    renderModal();

    await waitFor(() => {
      expect(screen.getByTestId("auto-rotate-checkbox").disabled).toBe(false);
    });

    // Trigger failure.
    fireEvent.click(screen.getByTestId("auto-rotate-checkbox"));
    await waitFor(() => {
      expect(screen.getByTestId("ocr-config-save-error")).toBeInTheDocument();
    });

    // Now make POST succeed.
    server.use(http.post("/api/ocr-config/auto-rotate", () => HttpResponse.json({})));

    // Trigger success.
    fireEvent.click(screen.getByTestId("auto-rotate-checkbox"));
    await waitFor(() => {
      expect(screen.queryByTestId("ocr-config-save-error")).toBeNull();
    });
  });

  it("no error banner when POST succeeds", async () => {
    server.use(http.post("/api/ocr-config/auto-rotate", () => HttpResponse.json({})));

    renderModal();

    await waitFor(() => {
      expect(screen.getByTestId("auto-rotate-checkbox").disabled).toBe(false);
    });

    fireEvent.click(screen.getByTestId("auto-rotate-checkbox"));

    // Wait a tick and confirm no error banner appears.
    await waitFor(() => {
      expect(screen.queryByTestId("ocr-config-save-error")).toBeNull();
    });
  });
});
