import { ApiError } from '@/core/api';

export type ApiFailureKey = 'unauthorized' | 'forbidden' | 'conflict' | 'serviceUnavailable' | 'requestFailed';

export function apiFailureKey(error: unknown): ApiFailureKey | null {
  if (!(error instanceof ApiError)) return null;
  if (error.status === 401) return 'unauthorized';
  if (error.status === 403) return 'forbidden';
  if (error.status === 409) return 'conflict';
  if (error.status >= 500) return 'serviceUnavailable';
  return 'requestFailed';
}
