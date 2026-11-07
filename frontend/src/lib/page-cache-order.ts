// A page refetch can finish after a newer refetch has already been stored.
// PagePayload.generation only increases, so an older payload must not replace
// a newer one. The map is per project, page, and line filter.

interface StoredPage<T> {
  generation: number;
  payload: T;
}

const accepted = new Map<string, StoredPage<{ generation?: number }>>();

export function pageCacheScope(projectId: string, pageIndex: number, filter: string): string {
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

/** Test isolation. The map lives for the life of the page module. */
export function resetPageCacheOrder(): void {
  accepted.clear();
}
