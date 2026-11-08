import type { QueryClient } from "@tanstack/react-query";

import { resetPageCacheOrderForProject } from "./page-cache-order";

/**
 * Establish a new response epoch after a completed page reload can restore
 * a page generation from the event-store head.
 */
export async function resetProjectPageCacheBoundary(
  queryClient: QueryClient,
  projectId: string,
): Promise<void> {
  await queryClient.cancelQueries({ queryKey: ["page", projectId] });
  resetPageCacheOrderForProject(projectId);
}
