// WordFooter.tsx — Sticky validate / skip / delete footer for WordDetail (P2.f).
// Spec: docs/plans/hifi-gaps-plan.md P2.f (Gap 41).
//
// Three-button footer pinned to the bottom of the word editor panel:
//   1. Validate  — toggles word.is_validated via POST .../validated
//   2. Skip      — walkSibling("next", page); no server call
//   3. Delete    — POST .../words/delete-batch (P1.3); requires ConfirmDialog
//
// data-testids:
//   word-footer                — outer container
//   word-footer-validate       — validate / unvalidate button
//   word-footer-skip           — skip (next word) button
//   word-footer-delete         — delete button (opens confirm)

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { KeyCap } from "@pdomain/pdomain-ui/primitives";
import { ConfirmDialog } from "../ConfirmDialog";
import { walkSibling } from "../../stores/selection-store";
import type { components } from "../../api/types";

type PagePayload = components["schemas"]["PagePayload"];
type ToggleValidatedRequest = components["schemas"]["ToggleValidatedRequest"];

// ─── internal helpers ─────────────────────────────────────────────────────────

async function apiPost<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    let message = res.statusText;
    try {
      const parsed = JSON.parse(text) as { message?: string };
      if (parsed.message) message = parsed.message;
    } catch {
      if (text) message = text;
    }
    throw Object.assign(new Error(message), { status: res.status });
  }
  return res.json() as Promise<T>;
}

// ─── hooks ────────────────────────────────────────────────────────────────────

function useToggleValidated(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<
    PagePayload,
    Error,
    { lineIndex: number; wordIndex: number; validated: boolean }
  >({
    mutationFn: ({ lineIndex, wordIndex, validated }) => {
      const body: ToggleValidatedRequest = { validated };
      return apiPost<PagePayload>(
        `/api/projects/${encodeURIComponent(projectId)}/pages/${encodeURIComponent(String(pageIndex))}/words/${encodeURIComponent(String(lineIndex))}/${encodeURIComponent(String(wordIndex))}/validated`,
        body,
      );
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// P1.3 (B-61): POSTs the real ``words/delete-batch`` route. The legacy
// page-scope ``/delete`` endpoint is an intentionally unimplemented 501
// stub — pointing here at it made the footer Delete confirm-then-delete-
// nothing (parity finding F5).
function useDeleteWord(projectId: string, pageIndex: number) {
  const qc = useQueryClient();
  return useMutation<PagePayload, Error, { lineIndex: number; wordIndex: number }>({
    mutationFn: ({ lineIndex, wordIndex }) =>
      apiPost<PagePayload>(
        `/api/projects/${encodeURIComponent(projectId)}/pages/${encodeURIComponent(String(pageIndex))}/words/delete-batch`,
        { scope: "word", word_indices: [[lineIndex, wordIndex]] },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["page", projectId, pageIndex] });
    },
  });
}

// ─── WordFooter ───────────────────────────────────────────────────────────────

export interface WordFooterProps {
  page: PagePayload;
  projectId: string;
  pageIndex: number;
  lineIndex: number;
  wordIndex: number;
  isValidated: boolean;
}

export function WordFooter({
  page,
  projectId,
  pageIndex,
  lineIndex,
  wordIndex,
  isValidated,
}: WordFooterProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);

  const toggleValidated = useToggleValidated(projectId, pageIndex);
  const deleteWord = useDeleteWord(projectId, pageIndex);

  function handleValidate() {
    toggleValidated.mutate({ lineIndex, wordIndex, validated: !isValidated });
  }

  function handleSkip() {
    walkSibling("next", page);
  }

  function handleDeleteConfirmed() {
    setConfirmOpen(false);
    deleteWord.mutate({ lineIndex, wordIndex });
  }

  return (
    <div
      data-testid="word-footer"
      className="sticky bottom-0 flex items-center gap-1 px-3 py-2 bg-surface border-t border-border-2"
    >
      {/* Validate / Unvalidate */}
      <button
        data-testid="word-footer-validate"
        onClick={handleValidate}
        disabled={toggleValidated.isPending}
        className={[
          "flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium transition-colors",
          "border",
          isValidated
            ? "border-accent/60 bg-accent/10 text-accent hover:bg-accent/20"
            : "border-border-2 bg-sunk text-ink-2 hover:bg-sunk/80",
        ].join(" ")}
        aria-label={isValidated ? "Unvalidate word" : "Validate word"}
      >
        <span>{isValidated ? "✓ Validated" : "Validate"}</span>
        <KeyCap keys="V" />
      </button>

      {/* Skip to next word */}
      <button
        data-testid="word-footer-skip"
        onClick={handleSkip}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium border border-border-2 bg-sunk text-ink-2 hover:bg-sunk/80 transition-colors"
        aria-label="Skip to next word"
      >
        <span>Skip</span>
        <KeyCap keys="Tab" />
      </button>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Delete */}
      <button
        data-testid="word-footer-delete"
        onClick={() => {
          setConfirmOpen(true);
        }}
        disabled={deleteWord.isPending}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium border border-mismatch/60 bg-mismatch/10 text-mismatch hover:bg-mismatch/20 transition-colors"
        aria-label="Delete word"
      >
        <span>Delete</span>
        <KeyCap keys={["⌫"]} />
      </button>

      <ConfirmDialog
        open={confirmOpen}
        title="Delete word?"
        message="This will permanently remove the word from the page. This action cannot be undone."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={handleDeleteConfirmed}
        onCancel={() => {
          setConfirmOpen(false);
        }}
      />
    </div>
  );
}
