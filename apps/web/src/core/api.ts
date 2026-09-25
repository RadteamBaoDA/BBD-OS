export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...options,
    cache: 'no-store',
    credentials: 'same-origin',
    headers: { ...options.headers },
  });
  if (response.status === 204) return undefined as T;

  const body = (await response.json()) as { error?: { message?: string } } & T;
  if (!response.ok) {
    throw new ApiError(response.status, body.error?.message ?? 'Request failed');
  }
  return body;
}

export function csrfHeaders(token: string): HeadersInit {
  return { 'X-CSRF-Token': token };
}
