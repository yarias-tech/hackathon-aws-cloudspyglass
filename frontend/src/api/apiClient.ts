import type { ErrorResponse } from "../types/errors";

const BASE_URL = "/api";

/**
 * Custom error class that wraps an ErrorResponse from the backend.
 * Provides typed access to error details and recoverability flag.
 */
export class ApiError extends Error {
  public readonly errorResponse: ErrorResponse;
  public readonly statusCode: number;

  constructor(statusCode: number, errorResponse: ErrorResponse) {
    super(errorResponse.message);
    this.name = "ApiError";
    this.statusCode = statusCode;
    this.errorResponse = errorResponse;
  }

  get recoverable(): boolean {
    return this.errorResponse.recoverable;
  }

  get errorCode(): string {
    return this.errorResponse.error_code;
  }
}

/**
 * Parse a non-2xx response into an ErrorResponse, or create a fallback
 * if the response body is not a valid ErrorResponse JSON.
 */
async function parseErrorResponse(
  response: Response
): Promise<ErrorResponse> {
  try {
    const body = await response.json();
    // Validate it has the expected shape
    if (
      typeof body === "object" &&
      body !== null &&
      "error_code" in body &&
      "message" in body &&
      "timestamp" in body &&
      "recoverable" in body
    ) {
      return body as ErrorResponse;
    }
  } catch {
    // Response body is not valid JSON — fall through to default
  }

  return {
    error_code: "UNKNOWN_ERROR",
    message: `Request failed with status ${response.status}`,
    details: null,
    timestamp: new Date().toISOString(),
    recoverable: response.status >= 500,
  };
}

/**
 * Shared API client for all frontend-to-backend communication.
 * All methods throw ApiError on non-2xx responses.
 */
export const apiClient = {
  async get<T>(path: string): Promise<T> {
    const response = await fetch(`${BASE_URL}${path}`);
    if (!response.ok) {
      const errorResponse = await parseErrorResponse(response);
      throw new ApiError(response.status, errorResponse);
    }
    return response.json() as Promise<T>;
  },

  async post<T>(path: string, body?: unknown): Promise<T> {
    const response = await fetch(`${BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!response.ok) {
      const errorResponse = await parseErrorResponse(response);
      throw new ApiError(response.status, errorResponse);
    }
    return response.json() as Promise<T>;
  },

  async put<T>(path: string, body?: unknown): Promise<T> {
    const response = await fetch(`${BASE_URL}${path}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!response.ok) {
      const errorResponse = await parseErrorResponse(response);
      throw new ApiError(response.status, errorResponse);
    }
    return response.json() as Promise<T>;
  },

  async delete<T>(path: string): Promise<T> {
    const response = await fetch(`${BASE_URL}${path}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      const errorResponse = await parseErrorResponse(response);
      throw new ApiError(response.status, errorResponse);
    }
    return response.json() as Promise<T>;
  },

  /**
   * Download a file from the API and trigger a browser save dialog.
   * Fetches the response as a blob, creates an object URL, and clicks
   * a temporary anchor element to initiate the download.
   */
  async download(path: string, filename: string): Promise<void> {
    const response = await fetch(`${BASE_URL}${path}`);
    if (!response.ok) {
      const errorResponse = await parseErrorResponse(response);
      throw new ApiError(response.status, errorResponse);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  },
};
