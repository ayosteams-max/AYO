import { MarkArrivedAttemptInvalidError, MarkArrivedContractError, MarkArrivedOutcomeUnknownError, MarkArrivedRejectedError, type MarkArrivedAttempt, type MarkArrivedRejection } from '../domain/courier-mark-arrived-command.ts';
import { PublicApiError } from './api-foundation.ts';
import type { CourierMarkArrivedCommandService } from './courier-mark-arrived-command.ts';
import { CourierMarkArrivedCommandScope, type MarkArrivedAttemptHandle } from './courier-mark-arrived-command-scope.ts';

type Service = Pick<CourierMarkArrivedCommandService, 'submit' | 'reconcile'>;
type Operation = { readonly handle: MarkArrivedAttemptHandle; readonly attempt: MarkArrivedAttempt; inFlight?: Promise<MarkArrivedControllerResult>; settled?: MarkArrivedControllerResult };
export type MarkArrivedControllerResult =
  | Readonly<{ outcome: 'applied' }> | Readonly<{ outcome: 'outcome_unknown' }> | Readonly<{ outcome: 'retry_same_attempt' }>
  | Readonly<{ outcome: 'rejected'; reason: MarkArrivedRejection | 'malformed_response' | 'refresh_required' | 'reconciliation_not_available' }>
  | Readonly<{ outcome: 'invalidated'; reason: 'invalid_handle' | 'non_current_operation' | 'scope_changed' | 'authority_lost' | 'state_changed' }>;

const unresolved = (operation: Operation) => !operation.settled || operation.settled.outcome === 'outcome_unknown' || operation.settled.outcome === 'retry_same_attempt';

export class CourierMarkArrivedController {
  private readonly scope: CourierMarkArrivedCommandScope;
  private readonly createService: () => Service | Promise<Service>;
  private service?: Promise<Service>;
  private operation?: Operation;
  constructor(scope: CourierMarkArrivedCommandScope, createService: () => Service | Promise<Service>) { this.scope = scope; this.createService = createService; }

  createAttempt(): MarkArrivedAttemptHandle | undefined {
    if (this.operation && unresolved(this.operation)) {
      if (this.scope.resolveForOperation(this.operation.handle)) return this.operation.handle;
      if (this.operation.inFlight) return undefined;
      this.operation.settled = Object.freeze({ outcome: 'invalidated', reason: 'invalid_handle' });
    }
    const handle = this.scope.createForCurrentPickup(); if (!handle) return undefined;
    const attempt = this.scope.resolveForSubmit(handle); if (!attempt) return undefined;
    this.operation = { handle, attempt }; return handle;
  }

  submit(handle: MarkArrivedAttemptHandle, signal?: AbortSignal): Promise<MarkArrivedControllerResult> {
    const operation = this.operation;
    if (!operation || operation.handle !== handle) return Promise.resolve(Object.freeze({ outcome: 'invalidated', reason: 'non_current_operation' }));
    if (operation.inFlight) return operation.inFlight;
    if (!this.scope.resolveForOperation(handle)) {
      const invalid = Object.freeze({ outcome: 'invalidated', reason: 'invalid_handle' } as const);
      operation.settled = invalid;
      return Promise.resolve(invalid);
    }
    if (operation.settled?.outcome === 'outcome_unknown') return Promise.resolve(operation.settled);
    if (operation.settled && operation.settled.outcome !== 'retry_same_attempt') return Promise.resolve(operation.settled);
    if (!this.scope.resolveForSubmit(handle)) return Promise.resolve(operation.settled = Object.freeze({ outcome: 'invalidated', reason: 'scope_changed' }));
    return this.flight(operation, this.executeSubmit(operation, signal));
  }

  reconcile(handle: MarkArrivedAttemptHandle, signal?: AbortSignal): Promise<MarkArrivedControllerResult> {
    const operation = this.operation;
    if (!operation || operation.handle !== handle) return Promise.resolve(Object.freeze({ outcome: 'invalidated', reason: 'invalid_handle' }));
    if (operation.inFlight) return operation.inFlight;
    if (!this.scope.resolveForOperation(handle)) {
      const invalid = Object.freeze({ outcome: 'invalidated', reason: 'invalid_handle' } as const);
      operation.settled = invalid;
      return Promise.resolve(invalid);
    }
    if (operation.settled?.outcome !== 'outcome_unknown') return Promise.resolve(operation.settled ?? Object.freeze({ outcome: 'rejected', reason: 'reconciliation_not_available' }));
    return this.flight(operation, this.executeReconcile(operation, signal));
  }

  private flight(operation: Operation, pending: Promise<MarkArrivedControllerResult>) {
    operation.inFlight = pending;
    void pending.then(() => { if (operation.inFlight === pending) operation.inFlight = undefined; }, () => { if (operation.inFlight === pending) operation.inFlight = undefined; });
    return pending;
  }
  private commandService() { return this.service ??= Promise.resolve(this.createService()); }
  private async executeSubmit(operation: Operation, signal?: AbortSignal): Promise<MarkArrivedControllerResult> {
    try { await (await this.commandService()).submit(operation.attempt, signal); this.scope.clearFreshForAttempt(operation.attempt); return operation.settled = Object.freeze({ outcome: 'applied' }); }
    catch (error) {
      if (error instanceof MarkArrivedOutcomeUnknownError) { this.scope.clearFreshForAttempt(operation.attempt); return operation.settled = Object.freeze({ outcome: 'outcome_unknown' }); }
      if (error instanceof MarkArrivedRejectedError) { this.scope.clearFreshForAttempt(operation.attempt); return operation.settled = Object.freeze({ outcome: 'rejected', reason: error.reason }); }
      if (error instanceof MarkArrivedContractError) { this.scope.clearFreshForAttempt(operation.attempt); return operation.settled = Object.freeze({ outcome: 'rejected', reason: 'malformed_response' }); }
      if (error instanceof MarkArrivedAttemptInvalidError) { this.scope.clearFreshForAttempt(operation.attempt); return operation.settled = Object.freeze({ outcome: 'invalidated', reason: 'scope_changed' }); }
      return this.boundPublicError(operation, error);
    }
  }
  private async executeReconcile(operation: Operation, signal?: AbortSignal): Promise<MarkArrivedControllerResult> {
    try {
      const value = await (await this.commandService()).reconcile(operation.attempt, signal);
      if (value.outcome === 'retry_same_attempt') {
        if (!this.scope.publishRetryEvidence(operation.attempt, value.pickup)) return operation.settled = Object.freeze({ outcome: 'invalidated', reason: 'scope_changed' });
        return operation.settled = Object.freeze({ outcome: 'retry_same_attempt' });
      }
      if (value.outcome === 'already_applied') {
        this.scope.clearFreshForAttempt(operation.attempt);
        return operation.settled = Object.freeze({ outcome: 'applied' });
      }
      return operation.settled = Object.freeze({ outcome: 'invalidated', reason: value.reason });
    } catch (error) {
      if (error instanceof MarkArrivedContractError) { this.scope.clearFreshForAttempt(operation.attempt); return operation.settled = Object.freeze({ outcome: 'rejected', reason: 'malformed_response' }); }
      if (error instanceof MarkArrivedAttemptInvalidError) { this.scope.clearFreshForAttempt(operation.attempt); return operation.settled = Object.freeze({ outcome: 'invalidated', reason: 'scope_changed' }); }
      if (error instanceof PublicApiError && (error.kind === 'request_cancelled' || error.status === undefined || error.status >= 500)) return operation.settled!;
      return this.boundPublicError(operation, error);
    }
  }
  private boundPublicError(operation: Operation, error: unknown): MarkArrivedControllerResult {
    if (!(error instanceof PublicApiError)) throw error;
    this.scope.clearFreshForAttempt(operation.attempt);
    const authority = error.status === 401 || error.status === 403 || error.status === 404 || ['authentication_required', 'session_expired', 'access_denied', 'not_found'].includes(error.kind);
    if (authority) return operation.settled = Object.freeze({ outcome: 'invalidated', reason: 'authority_lost' });
    return operation.settled = Object.freeze({ outcome: 'rejected', reason: error.kind === 'malformed_response' ? 'malformed_response' : 'refresh_required' });
  }
}
