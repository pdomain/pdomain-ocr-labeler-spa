// useBreadcrumbHotkeys.ts — Alt-arrow hierarchy navigation.
// Spec: docs/specs/2026-05-15-hifi-redesign-plan.md Slice 14.
//
// Shortcuts (active when no input/textarea is focused):
//   Alt+ArrowLeft  → walkSibling("prev", page)
//   Alt+ArrowRight → walkSibling("next", page)
//   Alt+ArrowUp    → walkLevel("up", page)
//   Alt+ArrowDown  → walkLevel("down", page)
//
// The page payload is captured by the caller — typically `ProjectPage`
// passes the current `pagePayload` so navigation operates on the
// currently-loaded page.

import { useEffect } from "react";
import { walkSibling, walkLevel } from "../stores/selection-store";
import type { components } from "../api/types";

type PagePayload = components["schemas"]["PagePayload"];

function isInputFocused(): boolean {
  const el = document.activeElement;
  if (!el) return false;
  const tag = el.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || (el as HTMLElement).isContentEditable;
}

export interface UseBreadcrumbHotkeysOptions {
  /** When undefined, the hook is a no-op (no page loaded). */
  page: PagePayload | undefined;
  /** Disable all breadcrumb hotkeys (e.g. while a modal is open). */
  enabled?: boolean;
}

export function useBreadcrumbHotkeys({ page, enabled = true }: UseBreadcrumbHotkeysOptions) {
  useEffect(() => {
    if (!enabled || !page) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (!e.altKey) return;
      if (e.ctrlKey || e.metaKey) return;
      if (isInputFocused()) return;
      if (!page) return;

      switch (e.key) {
        case "ArrowLeft":
          e.preventDefault();
          walkSibling("prev", page);
          break;
        case "ArrowRight":
          e.preventDefault();
          walkSibling("next", page);
          break;
        case "ArrowUp":
          e.preventDefault();
          walkLevel("up", page);
          break;
        case "ArrowDown":
          e.preventDefault();
          walkLevel("down", page);
          break;
        default:
          break;
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [page, enabled]);
}
