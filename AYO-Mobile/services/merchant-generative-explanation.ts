import type {
  MerchantGenerativeExplanationProvider,
  MerchantGenerativeExplanationRequest,
} from '../domain/merchant-generative-explanation.ts';
import { boundedFetch, parsePublicError, PublicApiError, validateApiBaseUrl } from './api-foundation.ts';
import type { SessionManager } from './session-manager.ts';

/** Canonical AYO-backend adapter only; it has no vendor, secret, retry, or command access. */
export class MerchantGenerativeExplanationService implements MerchantGenerativeExplanationProvider {
  private readonly baseUrl: string;
  private readonly sessions: SessionManager;
  private readonly request: typeof fetch;

  constructor(baseUrl: string, sessions: SessionManager, request: typeof fetch = fetch) {
    this.baseUrl = validateApiBaseUrl(baseUrl);
    this.sessions = sessions;
    this.request = request;
  }

  async generateExplanation(request: MerchantGenerativeExplanationRequest, signal?: AbortSignal): Promise<unknown> {
    const token = await this.sessions.accessToken();
    let response = await this.send(request, token, signal);
    if (response.status === 401) {
      const refreshed = await this.sessions.forceRefresh(token);
      if (!refreshed) throw new PublicApiError('session_expired', 401);
      response = await this.send(request, refreshed.accessToken, signal);
    }
    if (!response.ok) throw await parsePublicError(response);
    try { return await response.json(); }
    catch { throw new PublicApiError('malformed_response', response.status); }
  }

  private send(request: MerchantGenerativeExplanationRequest, token: string, signal?: AbortSignal) {
    const semantics = Object.freeze({
      promptVersion: request.promptVersion,
      locale: request.locale,
      recommendation: request.recommendation,
      reason: request.reason,
      userActionAvailable: request.userActionAvailable,
      tone: request.tone,
    });
    return boundedFetch(this.request, `${this.baseUrl}/mobile/merchant-intelligence/generative-explanation`, {
      method: 'POST',
      headers: { Accept: 'application/json', Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(semantics),
      signal,
    }, 3_000);
  }
}
