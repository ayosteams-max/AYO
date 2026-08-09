import {
  MerchantAcknowledgeArrivalAttemptInvalidError,
  MerchantAcknowledgeArrivalContractError,
  MerchantAcknowledgeArrivalOutcomeUnknownError,
  MerchantAcknowledgeArrivalRejectedError,
  type MerchantAcknowledgeArrivalAttempt,
  type MerchantAcknowledgeArrivalRejection,
} from '../domain/merchant-acknowledge-arrival-command.ts';
import { PublicApiError } from './api-foundation.ts';
import {
  MerchantAcknowledgeArrivalCommandScope,
  type MerchantAcknowledgeArrivalAttemptHandle,
} from './merchant-acknowledge-arrival-command-scope.ts';
import type {
  MerchantAcknowledgeArrivalCommandService,
  MerchantAcknowledgeArrivalDispatchObserver,
} from './merchant-acknowledge-arrival-command.ts';

type Service = Pick<MerchantAcknowledgeArrivalCommandService, 'reconcile'> & {
  submit(
    attempt: MerchantAcknowledgeArrivalAttempt,
    signal?: AbortSignal,
    onDispatch?: MerchantAcknowledgeArrivalDispatchObserver,
  ): ReturnType<MerchantAcknowledgeArrivalCommandService['submit']>;
};

export type MerchantAcknowledgeArrivalControllerResult =
  | Readonly<{ outcome: 'applied' }>
  | Readonly<{ outcome: 'outcome_unknown' }>
  | Readonly<{ outcome: 'retry_same_attempt' }>
  | Readonly<{
    outcome: 'rejected';
    reason: MerchantAcknowledgeArrivalRejection | 'refresh_required' | 'reconciliation_not_available';
  }>
  | Readonly<{
    outcome: 'invalidated';
    reason: 'scope_changed' | 'authority_lost' | 'state_changed';
  }>;

export type MerchantAcknowledgeArrivalControllerState =
  | Readonly<{ status: 'idle' }>
  | Readonly<{ status: 'submitting' }>
  | Readonly<{ status: 'reconciling' }>
  | Readonly<{ status: 'applied' }>
  | Readonly<{ status: 'outcome_unknown' }>
  | Readonly<{ status: 'retry_same_attempt' }>
  | Readonly<{ status: 'rejected'; reason: Extract<MerchantAcknowledgeArrivalControllerResult, { outcome: 'rejected' }>['reason'] }>
  | Readonly<{ status: 'invalidated'; reason: Extract<MerchantAcknowledgeArrivalControllerResult, { outcome: 'invalidated' }>['reason'] }>;

type Operation = {
  readonly generation: number;
  readonly handle: MerchantAcknowledgeArrivalAttemptHandle;
  readonly attempt: MerchantAcknowledgeArrivalAttempt;
  phase?: 'submitting' | 'reconciling';
  inFlight?: Promise<MerchantAcknowledgeArrivalControllerResult>;
  settled?: MerchantAcknowledgeArrivalControllerResult;
};

const frozen = <const T extends object>(value: T): Readonly<T> => Object.freeze(value);

/** High-integrity client operation custody. Backend authority remains final. */
export class MerchantAcknowledgeArrivalController {
  private readonly scope: MerchantAcknowledgeArrivalCommandScope;
  private readonly createService: () => Service | Promise<Service>;
  private readonly consumedVersions = new Map<string, number>();
  private service?: Promise<Service>;
  private operation?: Operation;
  private nextGeneration = 1;

  constructor(
    scope: MerchantAcknowledgeArrivalCommandScope,
    createService: () => Service | Promise<Service>,
  ) {
    this.scope = scope;
    this.createService = createService;
  }

  state(): MerchantAcknowledgeArrivalControllerState {
    const operation = this.operation;
    if (!operation) return frozen({ status: 'idle' });
    if (operation.phase) return frozen({ status: operation.phase });
    const settled = operation.settled;
    if (!settled) return frozen({ status: 'idle' });
    if (settled.outcome === 'rejected') return frozen({ status: 'rejected', reason: settled.reason });
    if (settled.outcome === 'invalidated') return frozen({ status: 'invalidated', reason: settled.reason });
    return frozen({ status: settled.outcome });
  }

  isAcknowledgeArrivalActionable(): boolean {
    const operation = this.operation;
    if (operation?.inFlight || operation?.settled?.outcome === 'outcome_unknown') return false;
    if (operation?.settled?.outcome === 'retry_same_attempt') {
      return this.scope.resolveForSubmit(operation.handle) !== undefined;
    }
    const current = this.scope.currentScope();
    return !!current && !this.consumedVersionSuppresses(current);
  }

  isReconciliationAvailable(): boolean {
    const operation = this.operation;
    return !!operation && !operation.inFlight && operation.settled?.outcome === 'outcome_unknown' &&
      this.scope.resolveForOperation(operation.handle) !== undefined;
  }

  acknowledgeArrival(signal?: AbortSignal): Promise<MerchantAcknowledgeArrivalControllerResult> {
    const existing = this.operation;
    if (existing?.inFlight) return existing.inFlight;
    if (existing?.settled?.outcome === 'outcome_unknown') return Promise.resolve(existing.settled);
    if (existing?.settled?.outcome === 'retry_same_attempt') return this.submit(existing, signal);

    const current = this.scope.currentScope();
    if (!current || this.consumedVersionSuppresses(current)) {
      if (existing?.settled?.outcome === 'applied') return Promise.resolve(existing.settled);
      return Promise.resolve(frozen({ outcome: 'invalidated', reason: 'scope_changed' }));
    }

    const handle = this.scope.createForCurrentPickup();
    if (!handle) return Promise.resolve(frozen({ outcome: 'invalidated', reason: 'scope_changed' }));
    const attempt = this.scope.resolveForSubmit(handle);
    if (!attempt) return Promise.resolve(frozen({ outcome: 'invalidated', reason: 'scope_changed' }));
    const operation: Operation = { generation: this.nextGeneration++, handle, attempt };
    this.operation = operation;
    return this.submit(operation, signal);
  }

  reconcileAcknowledgeArrival(signal?: AbortSignal): Promise<MerchantAcknowledgeArrivalControllerResult> {
    const operation = this.operation;
    if (!operation || operation.settled?.outcome !== 'outcome_unknown') {
      if (operation?.inFlight) return operation.inFlight;
      return Promise.resolve(frozen({ outcome: 'rejected', reason: 'reconciliation_not_available' }));
    }
    if (operation.inFlight) return operation.inFlight;
    if (!this.scope.resolveForOperation(operation.handle)) {
      return Promise.resolve(this.settle(operation, frozen({ outcome: 'invalidated', reason: 'scope_changed' })));
    }
    return this.flight(operation, 'reconciling', this.executeReconcile(operation, signal));
  }

  private submit(operation: Operation, signal?: AbortSignal): Promise<MerchantAcknowledgeArrivalControllerResult> {
    if (this.operation !== operation) return Promise.resolve(frozen({ outcome: 'invalidated', reason: 'scope_changed' }));
    if (operation.inFlight) return operation.inFlight;
    if (!this.scope.resolveForSubmit(operation.handle)) {
      return Promise.resolve(this.settle(operation, frozen({ outcome: 'invalidated', reason: 'scope_changed' })));
    }
    return this.flight(operation, 'submitting', this.executeSubmit(operation, signal));
  }

  private flight(
    operation: Operation,
    phase: 'submitting' | 'reconciling',
    pending: Promise<MerchantAcknowledgeArrivalControllerResult>,
  ): Promise<MerchantAcknowledgeArrivalControllerResult> {
    operation.phase = phase;
    operation.inFlight = pending;
    const clear = () => {
      if (this.operation === operation && operation.inFlight === pending) {
        operation.inFlight = undefined;
        operation.phase = undefined;
      }
    };
    void pending.then(clear, clear);
    return pending;
  }

  private commandService(): Promise<Service> {
    return this.service ??= Promise.resolve(this.createService());
  }

  private async executeSubmit(
    operation: Operation,
    signal?: AbortSignal,
  ): Promise<MerchantAcknowledgeArrivalControllerResult> {
    let mayHaveDispatched = false;
    try {
      await (await this.commandService()).submit(operation.attempt, signal, () => { mayHaveDispatched = true; });
      if (!this.scope.operationIsCurrent(operation.attempt)) {
        if (mayHaveDispatched) this.recordConsumed(operation);
        return this.settle(operation, frozen({ outcome: 'invalidated', reason: 'scope_changed' }));
      }
      this.recordConsumed(operation);
      this.scope.clearFreshForAttempt(operation.attempt);
      return this.settle(operation, frozen({ outcome: 'applied' }));
    } catch (error) {
      if (error instanceof MerchantAcknowledgeArrivalOutcomeUnknownError) {
        this.recordConsumed(operation);
        this.scope.clearFreshForAttempt(operation.attempt);
        return this.settle(operation, frozen({ outcome: 'outcome_unknown' }));
      }
      if (error instanceof MerchantAcknowledgeArrivalRejectedError) {
        this.scope.clearFreshForAttempt(operation.attempt);
        return this.settle(operation, frozen({ outcome: 'rejected', reason: error.reason }));
      }
      if (error instanceof MerchantAcknowledgeArrivalAttemptInvalidError) {
        if (mayHaveDispatched) this.recordConsumed(operation);
        this.scope.clearFreshForAttempt(operation.attempt);
        return this.settle(operation, frozen({ outcome: 'invalidated', reason: 'scope_changed' }));
      }
      if (error instanceof MerchantAcknowledgeArrivalContractError) {
        this.recordConsumed(operation);
        this.scope.clearFreshForAttempt(operation.attempt);
        return this.settle(operation, frozen({ outcome: 'outcome_unknown' }));
      }
      if (error instanceof PublicApiError) return this.boundPublicSubmitError(operation, error);
      this.recordConsumed(operation);
      this.settle(operation, frozen({ outcome: 'outcome_unknown' }));
      throw error;
    }
  }

  private async executeReconcile(
    operation: Operation,
    signal?: AbortSignal,
  ): Promise<MerchantAcknowledgeArrivalControllerResult> {
    try {
      const value = await (await this.commandService()).reconcile(operation.attempt, signal);
      if (!this.scope.operationIsCurrent(operation.attempt)) {
        return this.settle(operation, frozen({ outcome: 'invalidated', reason: 'scope_changed' }));
      }
      if (value.outcome === 'retry_same_attempt') {
        if (!this.scope.publishRetryEvidence(operation.attempt, value)) {
          return this.settle(operation, frozen({ outcome: 'invalidated', reason: 'scope_changed' }));
        }
        return this.settle(operation, frozen({ outcome: 'retry_same_attempt' }));
      }
      if (value.outcome === 'already_applied') {
        this.recordConsumed(operation);
        this.scope.clearFreshForAttempt(operation.attempt);
        return this.settle(operation, frozen({ outcome: 'applied' }));
      }
      this.scope.clearFreshForAttempt(operation.attempt);
      return this.settle(operation, frozen({ outcome: 'invalidated', reason: value.reason }));
    } catch (error) {
      if (error instanceof MerchantAcknowledgeArrivalAttemptInvalidError) {
        this.scope.clearFreshForAttempt(operation.attempt);
        return this.settle(operation, frozen({ outcome: 'invalidated', reason: 'scope_changed' }));
      }
      if (error instanceof PublicApiError) {
        const authorityLost = error.status === 401 || error.status === 403 || error.status === 404 ||
          ['authentication_required', 'session_expired', 'access_denied', 'not_found'].includes(error.kind);
        if (authorityLost) {
          this.scope.clearFreshForAttempt(operation.attempt);
          return this.settle(operation, frozen({ outcome: 'invalidated', reason: 'authority_lost' }));
        }
        if (error.kind === 'request_cancelled' || error.status === undefined || error.status >= 500) {
          return this.settle(operation, frozen({ outcome: 'outcome_unknown' }));
        }
      }
      if (error instanceof MerchantAcknowledgeArrivalContractError) {
        return this.settle(operation, frozen({ outcome: 'outcome_unknown' }));
      }
      this.settle(operation, frozen({ outcome: 'outcome_unknown' }));
      throw error;
    }
  }

  private boundPublicSubmitError(
    operation: Operation,
    error: PublicApiError,
  ): MerchantAcknowledgeArrivalControllerResult {
    this.scope.clearFreshForAttempt(operation.attempt);
    const authorityLost = error.status === 401 || error.status === 403 || error.status === 404 ||
      ['authentication_required', 'session_expired', 'access_denied', 'not_found'].includes(error.kind);
    if (authorityLost) return this.settle(operation, frozen({ outcome: 'invalidated', reason: 'authority_lost' }));
    if (error.kind === 'request_cancelled' || error.status === undefined || error.status >= 500 ||
      error.kind === 'malformed_response') {
      this.recordConsumed(operation);
      return this.settle(operation, frozen({ outcome: 'outcome_unknown' }));
    }
    return this.settle(operation, frozen({ outcome: 'rejected', reason: 'refresh_required' }));
  }

  private settle(
    operation: Operation,
    result: MerchantAcknowledgeArrivalControllerResult,
  ): MerchantAcknowledgeArrivalControllerResult {
    if (this.operation === operation && operation.generation === this.operation.generation) {
      operation.settled = result;
    }
    return result;
  }

  private recordConsumed(operation: Operation): void {
    if (this.operation !== operation) return;
    const key = this.consumedKey(operation.attempt);
    const prior = this.consumedVersions.get(key) ?? 0;
    this.consumedVersions.set(key, Math.max(prior, operation.attempt.expectedVersion));
  }

  private consumedVersionSuppresses(scope: NonNullable<ReturnType<MerchantAcknowledgeArrivalCommandScope['currentScope']>>): boolean {
    const key = [scope.identityId, scope.merchantId, scope.orderId, scope.pickupId]
      .map((value) => value.toLowerCase()).join(':');
    return scope.pickupVersion <= (this.consumedVersions.get(key) ?? 0);
  }

  private consumedKey(attempt: MerchantAcknowledgeArrivalAttempt): string {
    return [attempt.identityId, attempt.merchantId, attempt.orderId, attempt.pickupId].join(':');
  }
}
