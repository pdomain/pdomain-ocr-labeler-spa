import { describe, it, expect, beforeEach, vi } from "vitest";
import { ApiClient, ApiError } from "./client";
import { pageNoUrl } from "../lib/routes";

// ─── URL encoding tests ───────────────────────────────────────────────────────

describe("URL encoding", () => {
  describe("ApiClient.setCurrentPageIndex", () => {
    it("encodes a projectId containing a slash into the path", async () => {
      let capturedUrl = "";
      vi.stubGlobal(
        "fetch",
        vi.fn(async (url: RequestInfo | URL) => {
          capturedUrl = String(url);
          return new Response(JSON.stringify({}), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }),
      );

      const client = new ApiClient("http://localhost:8000");
      await client.setCurrentPageIndex("proj/with/slash", 0);

      expect(capturedUrl).toContain("proj%2Fwith%2Fslash");
      expect(capturedUrl).not.toMatch(/proj\/with\/slash/);
    });

    it("encodes a projectId containing a hash", async () => {
      let capturedUrl = "";
      vi.stubGlobal(
        "fetch",
        vi.fn(async (url: RequestInfo | URL) => {
          capturedUrl = String(url);
          return new Response(JSON.stringify({}), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }),
      );

      const client = new ApiClient("http://localhost:8000");
      await client.setCurrentPageIndex("proj#fragment", 2);

      expect(capturedUrl).toContain("proj%23fragment");
      expect(capturedUrl).not.toContain("proj#fragment");
    });
  });

  describe("pageNoUrl", () => {
    it("encodes a projectId containing a slash", () => {
      const url = pageNoUrl("my/project", 1);
      expect(url).toBe("/projects/my%2Fproject/pages/pageno/1");
    });

    it("encodes a projectId containing a hash", () => {
      const url = pageNoUrl("my#project", 3);
      expect(url).toBe("/projects/my%23project/pages/pageno/3");
    });

    it("encodes a projectId containing a question mark", () => {
      const url = pageNoUrl("my?project", 5);
      expect(url).toBe("/projects/my%3Fproject/pages/pageno/5");
    });

    it("leaves normal projectIds unchanged", () => {
      const url = pageNoUrl("myproject123", 2);
      expect(url).toBe("/projects/myproject123/pages/pageno/2");
    });
  });
});

describe("ApiClient", () => {
  let apiClient: ApiClient;

  beforeEach(() => {
    apiClient = new ApiClient("http://localhost:8000");
  });

  describe("error handling", () => {
    it("throws ApiError on non-2xx response with error body", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn(
          async () =>
            new Response(
              JSON.stringify({
                error: "validation_error",
                message: "invalid request",
                details: null,
              }),
              {
                status: 400,
                headers: { "Content-Type": "application/json" },
              },
            ),
        ),
      );

      try {
        await apiClient.get("/test");
        expect.fail("should have thrown ApiError");
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        const apiErr = err as ApiError;
        expect(apiErr.status).toBe(400);
        expect(apiErr.error).toBe("validation_error");
        expect(apiErr.message).toBe("invalid request");
        expect(apiErr.details).toBeNull();
      }
    });

    it("throws ApiError on 500 with details", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn(
          async () =>
            new Response(
              JSON.stringify({
                error: "internal_error",
                message: "something went wrong",
                details: ["line 1", "line 2", "line 3"],
              }),
              {
                status: 500,
                headers: { "Content-Type": "application/json" },
              },
            ),
        ),
      );

      try {
        await apiClient.get("/test");
        expect.fail("should have thrown ApiError");
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        const apiErr = err as ApiError;
        expect(apiErr.status).toBe(500);
        expect(apiErr.error).toBe("internal_error");
        expect(apiErr.details).toEqual(["line 1", "line 2", "line 3"]);
      }
    });

    it("throws ApiError on 404", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn(
          async () =>
            new Response(
              JSON.stringify({
                error: "http_404",
                message: "not found",
                details: null,
              }),
              {
                status: 404,
                headers: { "Content-Type": "application/json" },
              },
            ),
        ),
      );

      try {
        await apiClient.get("/test");
        expect.fail("should have thrown ApiError");
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        const apiErr = err as ApiError;
        expect(apiErr.status).toBe(404);
        expect(apiErr.error).toBe("http_404");
      }
    });

    it("throws ApiError with parsed body on non-JSON response", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn(
          async () =>
            new Response("Internal Server Error", {
              status: 500,
              headers: { "Content-Type": "text/plain" },
            }),
        ),
      );

      try {
        await apiClient.get("/test");
        expect.fail("should have thrown ApiError");
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        const apiErr = err as ApiError;
        expect(apiErr.status).toBe(500);
        expect(apiErr.message).toBe("Internal Server Error");
      }
    });
  });

  describe("falsy body serialization (Bug 1)", () => {
    it("sends body=0 as JSON string '0'", async () => {
      let capturedBody: string | null = null;
      vi.stubGlobal(
        "fetch",
        vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
          capturedBody = init?.body != null ? String(init.body) : null;
          return new Response(null, { status: 204 });
        }),
      );

      await apiClient.post<null>("/test", 0);

      expect(capturedBody).toBe("0");
    });

    it("sends body=false as JSON string 'false'", async () => {
      let capturedBody: string | null = null;
      vi.stubGlobal(
        "fetch",
        vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
          capturedBody = init?.body != null ? String(init.body) : null;
          return new Response(null, { status: 204 });
        }),
      );

      await apiClient.post<null>("/test", false);

      expect(capturedBody).toBe("false");
    });

    it("sends body='' as JSON string '\"\"'", async () => {
      let capturedBody: string | null = null;
      vi.stubGlobal(
        "fetch",
        vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
          capturedBody = init?.body != null ? String(init.body) : null;
          return new Response(null, { status: 204 });
        }),
      );

      await apiClient.post<null>("/test", "");

      expect(capturedBody).toBe('""');
    });

    it("does not send a body when options.body is undefined (GET)", async () => {
      let capturedBody: string | undefined = undefined;
      vi.stubGlobal(
        "fetch",
        vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
          capturedBody = init?.body !== undefined ? String(init.body) : undefined;
          return new Response(JSON.stringify({}), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }),
      );

      await apiClient.get("/test");

      expect(capturedBody).toBeUndefined();
    });
  });

  describe("empty / no-content response handling (Bug 2)", () => {
    it("returns null for a 204 No Content response without throwing", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn(async () => new Response(null, { status: 204 })),
      );

      const result = await apiClient.post<null>("/test", {});

      expect(result).toBeNull();
    });

    it("returns null for a 200 response with empty body (Content-Length: 0)", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn(
          async () =>
            new Response("", {
              status: 200,
              headers: { "Content-Length": "0" },
            }),
        ),
      );

      const result = await apiClient.post<null>("/test", {});

      expect(result).toBeNull();
    });

    it("still parses JSON body for normal 200 responses", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn(
          async () =>
            new Response(JSON.stringify({ ok: true }), {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }),
        ),
      );

      const result = await apiClient.get<{ ok: boolean }>("/test");

      expect(result).toEqual({ ok: true });
    });
  });
});
