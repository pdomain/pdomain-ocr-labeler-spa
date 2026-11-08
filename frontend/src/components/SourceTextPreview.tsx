import { useQuery } from "@tanstack/react-query";

import { fetchSourceTextPreview, type SourceTextPreview } from "../api/source-text";

export function useSourceTextPreview(projectId: string | undefined, pageIndex: number | undefined) {
  return useQuery<SourceTextPreview>({
    queryKey: ["source-text", projectId, pageIndex],
    queryFn: ({ signal }) => fetchSourceTextPreview(projectId ?? "", pageIndex ?? -1, signal),
    enabled:
      projectId !== undefined && projectId !== "" && pageIndex !== undefined && pageIndex >= 0,
    staleTime: 0,
  });
}
