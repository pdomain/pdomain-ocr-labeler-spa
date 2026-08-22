import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "../api/types";

export type TypographyHead = components["schemas"]["TypographyHeadResponse"];
export type TypographySubmission = components["schemas"]["TypographyCorrectionSubmission"];
export type TypographyReview = components["schemas"]["TypographyPageReviewResponse"];

export type TypographyWorklistResponse = components["schemas"]["TypographyWorklistResponse"];

export class TypographyApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new TypographyApiError(payload?.detail ?? response.statusText, response.status);
  }
  return response.json() as Promise<T>;
}

function pageBase(projectId: string, pageIndex: number): string {
  return `/api/projects/${encodeURIComponent(projectId)}/pages/${encodeURIComponent(String(pageIndex))}/typography`;
}

export function useTypographyHead(projectId: string, pageIndex: number, wordId?: string | null) {
  return useQuery({
    queryKey: ["typography-head", projectId, pageIndex, wordId],
    enabled: Boolean(wordId),
    queryFn: () => {
      if (!wordId) throw new TypographyApiError("Typography needs a stable word ID.", 400);
      return apiJson<TypographyHead>(
        `${pageBase(projectId, pageIndex)}/words/${encodeURIComponent(wordId)}/head`,
      );
    },
  });
}

export function useTypographyReview(projectId: string, pageIndex: number) {
  return useQuery({
    queryKey: ["typography-review", projectId, pageIndex],
    queryFn: () => apiJson<TypographyReview>(`${pageBase(projectId, pageIndex)}/review`),
  });
}

export function useTypographyWorklist(projectId: string, pageIndex: number) {
  return useQuery({
    queryKey: ["typography-worklist", projectId, pageIndex],
    queryFn: () =>
      apiJson<TypographyWorklistResponse>(`${pageBase(projectId, pageIndex)}/worklist`),
  });
}

export function useAppendTypographyCorrection(
  projectId: string,
  pageIndex: number,
  wordId: string,
) {
  const queryClient = useQueryClient();
  return useMutation<TypographyHead, TypographyApiError, TypographySubmission>({
    retry: false,
    mutationFn: (submission) =>
      apiJson<TypographyHead>(
        `${pageBase(projectId, pageIndex)}/words/${encodeURIComponent(wordId)}/corrections`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(submission),
        },
      ),
    onSuccess: (head) => {
      queryClient.setQueryData(["typography-head", projectId, pageIndex, wordId], head);
      void queryClient.invalidateQueries({ queryKey: ["typography-review", projectId, pageIndex] });
      void queryClient.invalidateQueries({
        queryKey: ["typography-worklist", projectId, pageIndex],
      });
    },
    onError: (error) => {
      if (error.status === 409) {
        void queryClient.invalidateQueries({
          queryKey: ["typography-head", projectId, pageIndex, wordId],
        });
      }
    },
  });
}
