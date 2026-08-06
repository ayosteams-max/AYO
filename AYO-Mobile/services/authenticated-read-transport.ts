import { boundedFetch, parsePublicError, PublicApiError, validateApiBaseUrl } from './api-foundation.ts';
import type { SessionManager } from './session-manager.ts';

export class AuthenticatedReadTransport {
  private readonly baseUrl: string;
  private readonly sessions: SessionManager;
  private readonly request: typeof fetch;
  constructor(baseUrl: string, sessions: SessionManager, request: typeof fetch = fetch) { this.baseUrl = validateApiBaseUrl(baseUrl); this.sessions = sessions; this.request = request; }
  async get(path: string, signal?: AbortSignal): Promise<unknown> {
    if (!path.startsWith('/') || path.startsWith('//')) throw new Error('invalid_api_path');
    const token = await this.sessions.accessToken();
    let response = await this.read(path, token, signal);
    if (response.status === 401) {
      const refreshed = await this.sessions.forceRefresh(token);
      if (!refreshed) throw new PublicApiError('session_expired', 401);
      response = await this.read(path, refreshed.accessToken, signal);
    }
    if (!response.ok) throw await parsePublicError(response);
    try { return await response.json(); } catch { throw new PublicApiError('malformed_response', response.status); }
  }
  private read(path: string, token: string, signal?: AbortSignal) {
    return boundedFetch(this.request, `${this.baseUrl}${path}`, { headers: { Accept: 'application/json', Authorization: `Bearer ${token}` }, signal });
  }
}
