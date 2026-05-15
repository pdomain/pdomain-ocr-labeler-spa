// toast.ts — thin wrapper around Sonner toast() with token-aware styling.
//
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 26
// Issue: (TBD)
//
// Provides typed helpers: toast.info(), toast.success(), toast.warn(), toast.error().
// Each maps to a Sonner toast with a 3px colored left border using token colors:
//   - info → --status-ocr
//   - success → --status-exact
//   - warn → --status-fuzzy
//   - error → --status-mismatch

import React from "react";
import { toast as sonnerToast, type ExternalToast } from "sonner";

/**
 * Maps toast level to its corresponding token color.
 */
const TOKEN_MAP: Record<"info" | "success" | "warn" | "error", string> = {
  info: "var(--status-ocr)",
  success: "var(--status-exact)",
  warn: "var(--status-fuzzy)",
  error: "var(--status-mismatch)",
};

/**
 * Info toast — uses --status-ocr token.
 * Supports all Sonner options (e.g., { id: "unique-id" }).
 */
export function info(message: string | React.ReactNode, options?: ExternalToast): string | number {
  return sonnerToast(message, {
    ...options,
    style: { borderLeft: `3px solid ${TOKEN_MAP.info}`, ...options?.style },
  });
}

/**
 * Success toast — uses --status-exact token.
 * Supports all Sonner options (e.g., { id: "unique-id" }).
 */
export function success(
  message: string | React.ReactNode,
  options?: ExternalToast,
): string | number {
  return sonnerToast(message, {
    ...options,
    style: { borderLeft: `3px solid ${TOKEN_MAP.success}`, ...options?.style },
  });
}

/**
 * Warning toast — uses --status-fuzzy token.
 * Supports all Sonner options (e.g., { id: "unique-id" }).
 */
export function warn(message: string | React.ReactNode, options?: ExternalToast): string | number {
  return sonnerToast(message, {
    ...options,
    style: { borderLeft: `3px solid ${TOKEN_MAP.warn}`, ...options?.style },
  });
}

/**
 * Error toast — uses --status-mismatch token.
 * Supports all Sonner options (e.g., { id: "unique-id" }).
 */
export function error(message: string | React.ReactNode, options?: ExternalToast): string | number {
  return sonnerToast(message, {
    ...options,
    style: { borderLeft: `3px solid ${TOKEN_MAP.error}`, ...options?.style },
  });
}

// Export namespace for ergonomic usage: toast.info("..."), etc.
export const toast = {
  info,
  success,
  warn,
  error,
};
