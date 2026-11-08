import type { ViewerCommand } from "../api/automation";

/**
 * Keep an acknowledged automation view visible until a later command replaces
 * it. Viewer acknowledgement clears only pending automation work, not the
 * page a person is currently inspecting.
 */
export function displayedViewerCommand(
  pending: ViewerCommand | null,
  observed: ViewerCommand | null,
): ViewerCommand | null {
  return pending ?? observed;
}
