import {
  MerchantAcknowledgeArrivalAttemptInvalidError,
  MerchantAcknowledgeArrivalContractError,
  MerchantAcknowledgeArrivalOutcomeUnknownError,
  MerchantAcknowledgeArrivalRejectedError,
  merchantAcknowledgeArrivalAttemptMatchesScope,
  parseMerchantAcknowledgeArrivalResult,
  reconcileMerchantAcknowledgeArrivalRead,
  type MerchantAcknowledgeArrivalAttempt,
  type MerchantAcknowledgeArrivalCommandScope,
  type MerchantAcknowledgeArrivalReconciliation,
  type MerchantAcknowledgeArrivalRejection,
  type MerchantAcknowledgeArrivalResult,
} from '../domain/merchant-acknowledge-arrival-command.ts';
import { boundedFetch, parsePublicError, PublicApiError, validateApiBaseUrl } from './api-foundation.ts';
import type { MerchantCourierPickupStatusService } from './merchant-courier-pickup-status.ts';
import type { SessionManager } from './session-manager.ts';

type ScopeReader = () => MerchantAcknowledgeArrivalCommandScope | undefined;
type OperationContinuity = (attempt: MerchantAcknowledgeArrivalAttempt) => boolean;
type DispatchGuard = () => boolean;

export class MerchantAcknowledgeArrivalTransport {
  private readonly baseUrl: string;
  private readonly sessions: SessionManager;
  private readonly request: typeof fetch;

  constructor(baseUrl: string, sessions: SessionManager, request: typeof fetch = fetch) {
    this.baseUrl = validateApiBaseUrl(baseUrl);
    this.sessions = sessions;
    this.request = request;
  }

  async post(attempt: MerchantAcknowledgeArrivalAttempt, dispatchAllowed: DispatchGuard, signal?: AbortSignal): Promise<unknown> {
    this.requireDispatchable(dispatchAllowed, signal);
    const session = await this.sessions.restore();
    if (!session || session.identityId.toLowerCase() !== attempt.identityId || session.sessionId.toLowerCase() !== attempt.sessionId) throw new MerchantAcknowledgeArrivalAttemptInvalidError();
    this.requireDispatchable(dispatchAllowed, signal);
    let response = await this.send(attempt, session.accessToken, signal);
    if (response.status === 401) {
      const refreshed = await this.sessions.forceRefresh(session.accessToken);
      if (!refreshed || refreshed.identityId.toLowerCase() !== attempt.identityId || refreshed.sessionId.toLowerCase() !== attempt.sessionId) throw new MerchantAcknowledgeArrivalAttemptInvalidError();
      this.requireDispatchable(dispatchAllowed, signal);
      response = await this.send(attempt, refreshed.accessToken, signal);
    }
    if (!response.ok) {
      if (response.status === 409) throw await parseMerchantAcknowledgeArrivalRejection(response);
      throw await parsePublicError(response);
    }
    try { return await response.json(); }
    catch { throw new PublicApiError('malformed_response', response.status); }
  }

  private send(attempt: MerchantAcknowledgeArrivalAttempt, token: string, signal?: AbortSignal) {
    return boundedFetch(this.request, `${this.baseUrl}/mobile/merchants/${encodeURIComponent(attempt.merchantId)}/courier-pickups/${encodeURIComponent(attempt.pickupId)}/acknowledge`, {
      method: 'POST',
      headers: {
        Accept: 'application/json', Authorization: `Bearer ${token}`, 'Content-Type': 'application/json',
        'Idempotency-Key': attempt.idempotencyKey,
      },
      body: JSON.stringify({ expected_version: attempt.expectedVersion, action: 'acknowledge_arrival' }),
      signal,
    });
  }

  private requireDispatchable(dispatchAllowed: DispatchGuard, signal?: AbortSignal) {
    if (signal?.aborted || !dispatchAllowed()) throw new MerchantAcknowledgeArrivalAttemptInvalidError();
  }
}

async function parseMerchantAcknowledgeArrivalRejection(response: Response): Promise<MerchantAcknowledgeArrivalRejectedError | PublicApiError> {
  let value: unknown;
  try { value = await response.json(); }
  catch { return new PublicApiError('temporarily_unavailable', response.status); }
  const envelope = value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
  const error = envelope?.error;
  const code = error && typeof error === 'object' && !Array.isArray(error) ? (error as Record<string, unknown>).code : undefined;
  const reasons: Readonly<Record<string, MerchantAcknowledgeArrivalRejection>> = {
    courier_pickup_version_conflict: 'version_conflict',
    courier_pickup_transition_not_allowed: 'transition_not_allowed',
    idempotency_conflict: 'idempotency_conflict',
    idempotency_replay_unavailable: 'replay_unavailable',
    courier_pickup_temporarily_unavailable: 'temporarily_unavailable',
  };
  return typeof code === 'string' && reasons[code]
    ? new MerchantAcknowledgeArrivalRejectedError(reasons[code])
    : new PublicApiError('temporarily_unavailable', response.status);
}

export class MerchantAcknowledgeArrivalCommandService {
  private readonly transport: Pick<MerchantAcknowledgeArrivalTransport, 'post'>;
  private readonly pickupStatus: Pick<MerchantCourierPickupStatusService, 'load'>;
  private readonly currentScope: ScopeReader;
  private readonly operationIsCurrent: OperationContinuity;

  constructor(
    transport: Pick<MerchantAcknowledgeArrivalTransport, 'post'>,
    pickupStatus: Pick<MerchantCourierPickupStatusService, 'load'>,
    currentScope: ScopeReader,
    operationIsCurrent: OperationContinuity = (attempt) => merchantAcknowledgeArrivalAttemptMatchesScope(attempt, currentScope()),
  ) {
    this.transport = transport;
    this.pickupStatus = pickupStatus;
    this.currentScope = currentScope;
    this.operationIsCurrent = operationIsCurrent;
  }

  async submit(attempt: MerchantAcknowledgeArrivalAttempt, signal?: AbortSignal): Promise<MerchantAcknowledgeArrivalResult> {
    if (!merchantAcknowledgeArrivalAttemptMatchesScope(attempt, this.currentScope())) throw new MerchantAcknowledgeArrivalAttemptInvalidError();
    try {
      const value = await this.transport.post(
        attempt,
        () => merchantAcknowledgeArrivalAttemptMatchesScope(attempt, this.currentScope()),
        signal,
      );
      if (!merchantAcknowledgeArrivalAttemptMatchesScope(attempt, this.currentScope())) throw new MerchantAcknowledgeArrivalAttemptInvalidError();
      return parseMerchantAcknowledgeArrivalResult(value, attempt);
    } catch (error) {
      if (error instanceof MerchantAcknowledgeArrivalContractError ||
        error instanceof PublicApiError && (error.kind === 'malformed_response' || error.kind === 'request_cancelled' || error.status === undefined || error.status >= 500)) {
        throw new MerchantAcknowledgeArrivalOutcomeUnknownError();
      }
      throw error;
    }
  }

  async reconcile(attempt: MerchantAcknowledgeArrivalAttempt, signal?: AbortSignal): Promise<MerchantAcknowledgeArrivalReconciliation> {
    if (!this.operationIsCurrent(attempt)) return Object.freeze({ outcome: 'invalidated', reason: 'authority_lost' });
    try {
      const pickup = await this.pickupStatus.load(attempt.merchantId, attempt.orderId, signal);
      if (!this.operationIsCurrent(attempt)) return Object.freeze({ outcome: 'invalidated', reason: 'authority_lost' });
      return reconcileMerchantAcknowledgeArrivalRead({
        pickup_id: pickup.pickupId,
        state: pickup.state,
        version: pickup.version,
        arrived_at: pickup.arrivedAt ?? null,
        merchant_acknowledged_at: pickup.merchantAcknowledgedAt ?? null,
        waiting_duration_seconds: pickup.waitingDurationSeconds ?? null,
        terminal_reason: pickup.terminalReason ?? null,
        updated_at: pickup.updatedAt,
        presentation_action: pickup.presentationAction,
      }, attempt);
    } catch (error) {
      if (
        error instanceof PublicApiError
        && (error.status === 403 || error.status === 404 || (error.status === 409 && error.kind === 'temporarily_unavailable'))
      ) return Object.freeze({ outcome: 'invalidated', reason: 'authority_lost' });
      throw error;
    }
  }
}
