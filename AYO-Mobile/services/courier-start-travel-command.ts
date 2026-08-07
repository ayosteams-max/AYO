import { attemptMatchesScope, parseStartTravelResult, reconcileStartTravelRead, StartTravelAttemptInvalidError, StartTravelOutcomeUnknownError, StartTravelRejectedError, type CourierCommandScope, type StartTravelAttempt, type StartTravelReconciliation, type StartTravelRejection, type StartTravelResult } from '../domain/courier-start-travel-command.ts';
import { boundedFetch, parsePublicError, PublicApiError, validateApiBaseUrl } from './api-foundation.ts';
import type { SessionManager } from './session-manager.ts';

type ScopeReader = () => CourierCommandScope | undefined;
type AuthenticatedRead = (path: string, signal?: AbortSignal) => Promise<unknown>;

export class CourierStartTravelTransport {
  private readonly baseUrl: string;
  private readonly sessions: SessionManager;
  private readonly request: typeof fetch;
  constructor(baseUrl: string, sessions: SessionManager, request: typeof fetch = fetch) { this.baseUrl = validateApiBaseUrl(baseUrl); this.sessions = sessions; this.request = request; }
  async post(attempt: StartTravelAttempt, signal?: AbortSignal): Promise<unknown> {
    const session = await this.sessions.restore();
    if (!session || session.identityId.toLowerCase() !== attempt.identityId || session.sessionId.toLowerCase() !== attempt.sessionId) throw new StartTravelAttemptInvalidError();
    let response = await this.send(attempt, session.accessToken, signal);
    if (response.status === 401) {
      const refreshed = await this.sessions.forceRefresh(session.accessToken);
      if (!refreshed || refreshed.identityId.toLowerCase() !== attempt.identityId || refreshed.sessionId.toLowerCase() !== attempt.sessionId) throw new StartTravelAttemptInvalidError();
      response = await this.send(attempt, refreshed.accessToken, signal);
    }
    if (!response.ok) {
      if (response.status === 409) throw await parseStartTravelRejection(response);
      throw await parsePublicError(response);
    }
    try { return await response.json(); } catch { throw new PublicApiError('malformed_response', response.status); }
  }
  private send(attempt: StartTravelAttempt, token: string, signal?: AbortSignal) {
    return boundedFetch(this.request, `${this.baseUrl}/mobile/courier-pickups/${encodeURIComponent(attempt.pickupId)}/actions`, {
      method: 'POST', headers: { Accept: 'application/json', Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', 'Idempotency-Key': attempt.idempotencyKey },
      body: JSON.stringify({ expected_version: attempt.expectedVersion, action: 'start_travel' }), signal,
    });
  }
}

async function parseStartTravelRejection(response: Response): Promise<StartTravelRejectedError | PublicApiError> {
  let value: unknown;
  try { value = await response.json(); } catch { return new PublicApiError('temporarily_unavailable', response.status); }
  const envelope = value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
  const detail = envelope?.detail;
  const code = detail && typeof detail === 'object' && !Array.isArray(detail) ? (detail as Record<string, unknown>).code : undefined;
  const reasons: Readonly<Record<string, StartTravelRejection>> = {
    courier_pickup_version_conflict: 'version_conflict', courier_pickup_transition_not_allowed: 'transition_not_allowed',
    idempotency_conflict: 'idempotency_conflict', idempotency_replay_unavailable: 'replay_unavailable',
  };
  return typeof code === 'string' && reasons[code] ? new StartTravelRejectedError(reasons[code]) : new PublicApiError('temporarily_unavailable', response.status);
}

export class CourierStartTravelCommandService {
  private readonly transport: Pick<CourierStartTravelTransport, 'post'>;
  private readonly read: AuthenticatedRead;
  private readonly currentScope: ScopeReader;
  constructor(transport: Pick<CourierStartTravelTransport, 'post'>, read: AuthenticatedRead, currentScope: ScopeReader) { this.transport = transport; this.read = read; this.currentScope = currentScope; }
  async submit(attempt: StartTravelAttempt, signal?: AbortSignal): Promise<StartTravelResult> {
    if (!attemptMatchesScope(attempt, this.currentScope())) throw new StartTravelAttemptInvalidError();
    let value: unknown;
    try { value = await this.transport.post(attempt, signal); }
    catch (error) {
      if (error instanceof PublicApiError && (error.kind === 'request_cancelled' || error.status === undefined || error.status >= 500)) throw new StartTravelOutcomeUnknownError();
      throw error;
    }
    if (!attemptMatchesScope(attempt, this.currentScope())) throw new StartTravelAttemptInvalidError();
    return parseStartTravelResult(value, attempt);
  }
  async reconcile(attempt: StartTravelAttempt, signal?: AbortSignal): Promise<StartTravelReconciliation> {
    if (!attemptMatchesScope(attempt, this.currentScope())) return Object.freeze({ outcome: 'invalidated', reason: 'authority_lost' });
    try {
      const value = await this.read(`/mobile/courier-pickups/${encodeURIComponent(attempt.pickupId)}`, signal);
      if (!attemptMatchesScope(attempt, this.currentScope())) return Object.freeze({ outcome: 'invalidated', reason: 'authority_lost' });
      return reconcileStartTravelRead(value, attempt);
    } catch (error) {
      if (error instanceof PublicApiError && (error.status === 403 || error.status === 404)) return Object.freeze({ outcome: 'invalidated', reason: 'authority_lost' });
      throw error;
    }
  }
}
