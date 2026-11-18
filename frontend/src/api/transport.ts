export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}
export type ErrorType<T> = ApiError & { details?: T };
export type BodyType<T> = T;

export async function apiFetch<T>(
  url: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body instanceof FormData) headers.delete("Content-Type");
  const response = await fetch(url, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    let message = "The server could not complete this request.";
    if (payload && typeof payload === "object" && "detail" in payload) {
      const detail = payload.detail;
      if (typeof detail === "string") message = detail;
      else if (Array.isArray(detail))
        message = detail
          .map((entry: unknown) =>
            entry && typeof entry === "object" && "msg" in entry
              ? String(entry.msg)
              : "Invalid input",
          )
          .join("; ");
    }
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  if (response.headers.get("Content-Type")?.includes("image/"))
    return (await response.blob()) as T;
  return response.json() as Promise<T>;
}
