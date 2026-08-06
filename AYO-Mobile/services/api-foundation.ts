export type PublicErrorKind =
  | 'authentication_required' | 'access_denied' | 'session_expired' | 'feature_unavailable'
  | 'not_found' | 'temporarily_unavailable' | 'malformed_response' | 'request_cancelled';

export class PublicApiError extends Error {
  readonly kind: PublicErrorKind;
  readonly status?: number;
  constructor(kind: PublicErrorKind, status?: number) { super(kind); this.kind = kind; this.status = status; }
}

export function validateApiBaseUrl(value: string): string {
  const normalized = value.replace(/\/$/, '');
  const url = new URL(normalized);
  const loopback = url.protocol === 'http:' && ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname);
  if (url.protocol !== 'https:' && !loopback) throw new Error('secure_api_url_required');
  if (url.username || url.password || url.search || url.hash) throw new Error('invalid_api_url');
  return normalized;
}

const publicCodes: Readonly<Record<string, PublicErrorKind>> = {
  authentication_required: 'authentication_required',
  authentication_failed: 'access_denied',
  refresh_denied: 'session_expired',
  feature_unavailable: 'feature_unavailable',
  not_found: 'not_found',
  temporarily_unavailable: 'temporarily_unavailable',
  authentication_rate_limited: 'temporarily_unavailable',
};

export async function parsePublicError(response: Response): Promise<PublicApiError> {
  let value: unknown;
  try { value = await response.json(); } catch { return new PublicApiError('temporarily_unavailable', response.status); }
  if (!value || typeof value !== 'object' || Array.isArray(value)) return new PublicApiError('temporarily_unavailable', response.status);
  const envelope = value as Record<string, unknown>;
  const body = envelope.error ?? envelope.detail;
  const code = body && typeof body === 'object' && !Array.isArray(body) ? (body as Record<string, unknown>).code : undefined;
  return new PublicApiError(typeof code === 'string' ? (publicCodes[code] ?? 'temporarily_unavailable') : 'temporarily_unavailable', response.status);
}

export async function boundedFetch(request: typeof globalThis.fetch, input: string, init: RequestInit = {}, timeoutMs = 10_000) {
  const timeout = new AbortController();
  const abort = () => timeout.abort();
  if (init.signal?.aborted) timeout.abort();
  else init.signal?.addEventListener('abort', abort, { once: true });
  const timer = setTimeout(abort, timeoutMs);
  try {
    return await request(input, { ...init, signal: timeout.signal });
  } catch (error) {
    if (timeout.signal.aborted) throw new PublicApiError('request_cancelled');
    throw new PublicApiError('temporarily_unavailable');
  } finally {
    clearTimeout(timer);
    init.signal?.removeEventListener('abort', abort);
  }
}
