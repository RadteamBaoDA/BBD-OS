export class ApiError extends Error {
  readonly code: string | null;
  readonly details: unknown;
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
    sessionRefresh ??= apiRequest<Session>('/api/v1/auth/session')
      .then((session) => {
        window.dispatchEvent(new CustomEvent('bbd:session-refreshed', { detail: session }));
        return session;
      })
      .finally(() => { sessionRefresh = null; });
    const session = await sessionRefresh;
    headers.set('X-CSRF-Token', session.csrfToken);
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

export function csrfHeaders(token: string): HeadersInit {
  return { 'X-CSRF-Token': token };
}
