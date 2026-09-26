export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
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

  const body = (await response.json()) as { error?: { message?: string } } & T;
  if (!response.ok) {
    if (response.status === 401 && typeof window !== 'undefined') {
      window.dispatchEvent(new Event('bbd:unauthorized'));
    }
    throw new ApiError(response.status, body.error?.message ?? 'Request failed');
  }
  return body;
}

export function csrfHeaders(token: string): HeadersInit {
  return { 'X-CSRF-Token': token };
}
