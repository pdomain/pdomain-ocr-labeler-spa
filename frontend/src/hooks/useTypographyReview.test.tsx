import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { server } from "../test/server";
import { useAppendTypographyCorrection, useTypographyHead } from "./useTypographyReview";

function wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      {children}
    </QueryClientProvider>
  );
}

describe("typography review hooks", () => {
  it("loads the server-provided extended grapheme map", async () => {
    server.use(
      http.get("/api/projects/p1/pages/0/typography/words/w1/head", () =>
        HttpResponse.json({ word_id: "w1", text: "á👨‍👩‍👧‍👦", graphemes: ["á", "👨‍👩‍👧‍👦"] }),
      ),
    );
    const { result } = renderHook(() => useTypographyHead("p1", 0, "w1"), { wrapper });
    await waitFor(() => expect(result.current.data?.graphemes).toEqual(["á", "👨‍👩‍👧‍👦"]));
  });

  it("surfaces stale-head 409 without retrying the correction", async () => {
    let posts = 0;
    server.use(
      http.post("/api/projects/p1/pages/0/typography/words/w1/corrections", () => {
        posts += 1;
        return HttpResponse.json({ detail: "typography head is stale" }, { status: 409 });
      }),
    );
    const { result } = renderHook(() => useAppendTypographyCorrection("p1", 0, "w1"), {
      wrapper,
    });
    await act(async () => {
      await expect(
        result.current.mutateAsync({ expected_head: "0".repeat(64) } as never),
      ).rejects.toMatchObject({ status: 409 });
    });
    expect(posts).toBe(1);
  });
});
