// A page refetch can finish after a newer refetch has already been stored.
// PagePayload.generation only increases, so an older payload must not replace
// a newer one. The map is per project, page, and line filter.

interface StoredPage<T> {
  generation: number;
  payload: T;
}

const accepted = new Map<string, StoredPage<{ generation?: number }>>();
const projectEpochs = new Map<string, number>();

export function pageCacheScope(projectId: string, pageIndex: number, filter: string): string {
  pageCacheEpoch(projectId);
  return `${projectId}\0${String(pageIndex)}\0${filter}`;
}

function generationOf(payload: { generation?: number }): number {
  const generation = payload.generation;
  return typeof generation === "number" && Number.isFinite(generation) ? generation : 0;
}

/**
 * Keep the newest page payload seen for `scope`.
 * An equal generation is a replacement and wins. A strictly older generation
 * is discarded and the stored payload is returned instead.
 */
export function acceptPagePayload<T extends { generation?: number }>(
  scope: string,
  incoming: T,
): T {
  const generation = generationOf(incoming);
  const stored = accepted.get(scope);
  if (stored !== undefined && generation < stored.generation) {
    return stored.payload as T;
  }
  accepted.set(scope, { generation, payload: incoming });
  return incoming;
}

/** Start a new response epoch for every project tracked by this page-cache module. */
export function resetPageCacheOrder(): void {
  accepted.clear();
  for (const [projectId, epoch] of projectEpochs) projectEpochs.set(projectId, epoch + 1);
}

/**
 * A project load can restart every page generation at zero. Canceling the
 * affected requests before this call prevents responses from the previous
 * loaded project state from crossing that epoch boundary.
 */
export function resetPageCacheOrderForProject(projectId: string): void {
  const prefix = `${projectId}\0`;
  for (const scope of accepted.keys()) {
    if (scope.startsWith(prefix)) accepted.delete(scope);
  }
  projectEpochs.set(projectId, pageCacheEpoch(projectId) + 1);
}

/** The current response epoch for one project. */
export function pageCacheEpoch(projectId: string): number {
  const epoch = projectEpochs.get(projectId);
  if (epoch !== undefined) return epoch;
  projectEpochs.set(projectId, 0);
  return 0;
}

/** A response started before a project reload must not commit afterwards. */
export function isCurrentPageCacheEpoch(projectId: string, epoch: number): boolean {
  return epoch === pageCacheEpoch(projectId);
}
