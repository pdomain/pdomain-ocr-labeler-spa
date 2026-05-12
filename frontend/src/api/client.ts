/**
 * Thin fetch wrapper for API calls.
 * - Base URL from window.__ENV__.API_BASE
 * - JSON serialization and Content-Type header
 * - Throws ApiError on non-2xx responses
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    public error: string,
    public message: string,
    public details?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    method: string,
    path: string,
    options?: {
      body?: unknown;
    }
  ): Promise<T> {
    const url = new URL(path, this.baseUrl).toString();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };

    const fetchOptions: RequestInit = {
      method,
      headers,
    };

    if (options?.body) {
      fetchOptions.body = JSON.stringify(options.body);
    }

    const response = await fetch(url, fetchOptions);

    if (!response.ok) {
      let errorData: {
        error?: string;
        message?: string;
        details?: unknown;
      } = {};
      let message = response.statusText;
      const text = await response.text();

      try {
        if (text) {
          errorData = JSON.parse(text);
          message = errorData.message || response.statusText;
        }
      } catch {
        // If response is not JSON, use text as message
        if (text) {
          message = text;
        }
      }

      throw new ApiError(
        response.status,
        errorData.error || `http_${response.status}`,
        message,
        errorData.details
      );
    }

    return response.json();
  }

  get<T>(path: string): Promise<T> {
    return this.request<T>("GET", path);
  }

  post<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>("POST", path, { body });
  }

  put<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>("PUT", path, { body });
  }

  delete<T>(path: string): Promise<T> {
    return this.request<T>("DELETE", path);
  }
}
