/** Represents an unsuccessful API response with its HTTP status and optional machine-readable error details. */
export class ApiError extends Error {
  readonly code: string | null;
  readonly details: unknown;
  /** Copies the response status, message, and recognized payload fields onto the error. */
  constructor(
    readonly status: number,
    message: string,
    payload?: { code?: unknown; details?: unknown },
  ) {
    super(message);
    this.code = typeof payload?.code === 'string' ? payload.code : null;
    this.details = payload?.details;
  }
}

type Session = { authenticated: true; csrfToken: string };
let sessionRefresh: Promise<Session> | null = null;

/** Sends a same-origin API request, applies the provided request options, and rejects unsuccessful responses as ApiError. */
export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  retryCsrf = true,
): Promise<T> {
  const headers = new Headers(options.headers);
  const response = await fetch(path, {
    ...options,
    cache: 'no-store',
    credentials: 'same-origin',
    headers,
  });
  if (
    retryCsrf && response.status === 403 &&
    response.headers.get('X-CSRF-Error') === 'invalid' &&
    headers.has('X-CSRF-Token') &&
    !['GET', 'HEAD'].includes((options.method ?? 'GET').toUpperCase())
  ) {
    // Share one session refresh across concurrent rejected mutations to avoid competing CSRF rotations.
    sessionRefresh ??= apiRequest<Session>('/api/v1/auth/session')
      .then((session) => {
        window.dispatchEvent(new CustomEvent('bbd:session-refreshed', { detail: session }));
        return session;
      })
      .finally(() => { sessionRefresh = null; });
    const session = await sessionRefresh;
    headers.set('X-CSRF-Token', session.csrfToken);
    // Disable further CSRF retries so a failed refresh cannot recurse indefinitely.
    return apiRequest<T>(path, { ...options, headers }, false);
  }
  if (response.status === 204) return undefined as T;

  const body = (await response.json()) as { error?: { message?: string; code?: string; details?: unknown }; detail?: string | { message?: string; code?: string; details?: unknown } } & T;
  if (!response.ok) {
    if (response.status === 401 && typeof window !== 'undefined') {
      window.dispatchEvent(new Event('bbd:unauthorized'));
    }
    const detail = typeof body.detail === 'object' && body.detail !== null ? body.detail : undefined;
    const message = body.error?.message ?? detail?.message ?? (typeof body.detail === 'string' ? body.detail : 'Request failed');
    throw new ApiError(response.status, message, body.error ?? detail);
  }
  return body;
}

/** Builds the request headers used to submit the supplied CSRF token. */
export function csrfHeaders(token: string): HeadersInit {
  return { 'X-CSRF-Token': token };
}
