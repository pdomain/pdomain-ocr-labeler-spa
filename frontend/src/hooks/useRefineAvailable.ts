// useRefineAvailable.ts — FO-9 capability probe.
//
// Fetches GET /api/refine/available once (stale-while-revalidate) and
// returns `{ available, reason }`.  The ErasePixelsSection component
// reads `available` to decide whether to enable its Apply button.
//
// The probe always returns { available: false } until the OCR engine is
// wired in M3-proper.  The query is kept alive for the lifetime of the
// page so the button reacts if the server is restarted with a wired engine.

import { useQuery } from "@tanstack/react-query";
import type { components } from "../api/types";

type RefineAvailableResponse = components["schemas"]["RefineAvailableResponse"];

async function fetchRefineAvailable(): Promise<RefineAvailableResponse> {
  const res = await fetch("/api/refine/available");
  if (!res.ok) {
    // Treat network errors as "not available" so the button stays disabled
    // rather than crashing the whole panel.
    return { available: false, reason: `probe failed: ${res.statusText}` };
  }
  return res.json() as Promise<RefineAvailableResponse>;
}

/**
 * Probe whether the OCR bbox refinement engine is available on the server.
 *
 * Returns `{ available: false, reason: "..." }` until M3-proper wires the OCR
 * adapter.  The ErasePixelsSection uses this to control the Apply button.
 */
export function useRefineAvailable() {
  return useQuery<RefineAvailableResponse>({
    queryKey: ["refine-available"],
    queryFn: fetchRefineAvailable,
    // Probe once per session; capability won't change without a server restart.
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}
