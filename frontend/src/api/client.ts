// Small fetch wrapper. Every API failure becomes an ApiError with a message that is safe to show.

const BASE_URL: string = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;

  constructor(status: number, code: string, message: string, details: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const UNREACHABLE = "Cannot reach the API. Check that the backend is running (see the README) and try again.";

export type Query = Record<string, string | number | boolean | undefined | null | (string | number)[]>;

export function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((item) => params.append(key, String(item)));
    else params.append(key, String(value));
  }
  const text = params.toString();
  return `${BASE_URL}/api${path}${text ? `?${text}` : ""}`;
}

/** Turn the backend's error envelope (or anything else) into an ApiError. */
async function toApiError(response: Response): Promise<ApiError> {
  try {
    const body = await response.json();
    const error = body?.error;
    if (error?.message) {
      let message: string = error.message;
      if (Array.isArray(error.details) && error.details[0]?.problem) {
        message += ` (${error.details[0].field}: ${error.details[0].problem})`;
      }
      return new ApiError(response.status, error.code ?? "error", message, error.details ?? null);
    }
  } catch {
    // not JSON - fall through
  }
  // A gateway error without our JSON envelope means the API itself is down (for example behind the dev proxy).
  if ([502, 503, 504].includes(response.status)) return new ApiError(response.status, "network_error", UNREACHABLE);
  return new ApiError(response.status, "http_error", `The server answered with status ${response.status}.`);
}

interface SendOptions {
  query?: Query;
  body?: unknown;
  signal?: AbortSignal;
  file?: File;
}

async function send(method: string, path: string, options: SendOptions = {}): Promise<Response> {
  let init: RequestInit = { method, signal: options.signal };
  if (options.file) {
    const form = new FormData();
    form.append("file", options.file);
    init = { ...init, body: form };
  } else if (options.body !== undefined) {
    init = { ...init, headers: { "Content-Type": "application/json" }, body: JSON.stringify(options.body) };
  }
  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), init);
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError(0, "network_error", UNREACHABLE);
  }
  if (!response.ok) throw await toApiError(response);
  return response;
}

export async function getJson<T>(path: string, query?: Query, signal?: AbortSignal): Promise<T> {
  return (await send("GET", path, { query, signal })).json() as Promise<T>;
}

export async function postJson<T>(path: string, body: unknown = {}): Promise<T> {
  return (await send("POST", path, { body })).json() as Promise<T>;
}

export async function patchJson<T>(path: string, body: unknown): Promise<T> {
  return (await send("PATCH", path, { body })).json() as Promise<T>;
}

export async function uploadFile<T>(path: string, file: File): Promise<T> {
  return (await send("POST", path, { file })).json() as Promise<T>;
}

export async function deleteRequest(path: string): Promise<void> {
  await send("DELETE", path);
}

/** Download a file from the API and hand it to the browser as a save-as. */
export async function downloadFile(path: string, query: Query, fallbackName: string): Promise<void> {
  const response = await send("GET", path, { query });
  const disposition = response.headers.get("content-disposition") ?? "";
  const match = /filename="?([^";]+)"?/i.exec(disposition);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = match?.[1] ?? fallbackName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}
