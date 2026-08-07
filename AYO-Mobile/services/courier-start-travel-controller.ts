import {
  StartTravelAttemptInvalidError,
  StartTravelContractError,
  StartTravelOutcomeUnknownError,
  StartTravelRejectedError,
  type StartTravelAttempt,
  type StartTravelRejection,
} from '../domain/courier-start-travel-command.ts';
import { PublicApiError } from './api-foundation.ts';
import type { CourierStartTravelCommandService } from './courier-start-travel-command.ts';
import { CourierStartTravelCommandScope, type StartTravelAttemptHandle } from './courier-start-travel-command-scope.ts';

type CommandService = Pick<CourierStartTravelCommandService, 'submit' | 'reconcile'>;
type CommandServiceFactory = () => CommandService | Promise<CommandService>;

export type StartTravelControllerResult =
  | Readonly<{ outcome: 'applied' }>
  | Readonly<{ outcome: 'outcome_unknown' }>
  | Readonly<{ outcome: 'retry_same_attempt' }>
  | Readonly<{ outcome: 'rejected'; reason: StartTravelRejection | 'malformed_response' | 'refresh_required' | 'reconciliation_not_available' }>
  | Readonly<{ outcome: 'invalidated'; reason: 'invalid_handle' | 'non_current_operation' | 'scope_changed' | 'authority_lost' | 'state_changed' }>;

type Operation = {
  readonly handle: StartTravelAttemptHandle;
  readonly attempt: StartTravelAttempt;
  inFlight?: Promise<StartTravelControllerResult>;
  settled?: StartTravelControllerResult;
};

const unresolved = (operation: Operation) => !operation.settled || operation.settled.outcome === 'outcome_unknown' || operation.settled.outcome === 'retry_same_attempt';

/** Trusted, scope-instance-bound orchestration. No presentation submit capability is exported. */
export class CourierStartTravelController {
  private readonly scope: CourierStartTravelCommandScope;
  private readonly createService: CommandServiceFactory;
  private service?: Promise<CommandService>;
  private operation?: Operation;

  constructor(scope: CourierStartTravelCommandScope, createService: CommandServiceFactory) {
    this.scope = scope;
    this.createService = createService;
  }

  createAttempt(): StartTravelAttemptHandle | undefined {
    const existing = this.operation;
    if (existing && unresolved(existing)) {
      if (existing.handle.isCurrent()) return existing.handle;
      if (existing.inFlight || existing.settled?.outcome === 'outcome_unknown' || existing.settled?.outcome === 'retry_same_attempt') return undefined;
    }
    const handle = this.scope.createForCurrentPickup();
    if (!handle) return undefined;
    const attempt = this.scope.resolveForTrustedUse(handle);
    if (!attempt) return undefined;
    this.operation = { handle, attempt };
    return handle;
  }

  canCreateAttempt(): boolean {
    const existing = this.operation;
    if (existing && unresolved(existing)) {
      if (existing.handle.isCurrent()) return true;
      if (existing.inFlight || existing.settled?.outcome === 'outcome_unknown' || existing.settled?.outcome === 'retry_same_attempt') return false;
    }
    return this.scope.currentScope() !== undefined;
  }

  submit(handle: StartTravelAttemptHandle, signal?: AbortSignal): Promise<StartTravelControllerResult> {
    const attempt = this.scope.resolveForTrustedUse(handle);
    if (!attempt) return Promise.resolve(Object.freeze({ outcome: 'invalidated', reason: 'invalid_handle' }));
    const operation = this.operation;
    if (!operation || operation.handle !== handle || operation.attempt !== attempt) {
      return Promise.resolve(Object.freeze({ outcome: 'invalidated', reason: 'non_current_operation' }));
    }
    if (operation.inFlight) return operation.inFlight;
    if (operation.settled?.outcome === 'outcome_unknown') return Promise.resolve(operation.settled);
    if (operation.settled && operation.settled.outcome !== 'retry_same_attempt') {
      return Promise.resolve(operation.settled);
    }
    const pending = this.executeSubmit(operation, signal);
    operation.inFlight = pending;
    const clearFlight = () => { if (operation?.inFlight === pending) operation.inFlight = undefined; };
    void pending.then(clearFlight, clearFlight);
    return pending;
  }

  reconcile(handle: StartTravelAttemptHandle, signal?: AbortSignal): Promise<StartTravelControllerResult> {
    const operation = this.operation;
    const attempt = this.scope.resolveForTrustedUse(handle);
    if (!operation || operation.handle !== handle || !attempt || attempt !== operation.attempt) {
      return Promise.resolve(Object.freeze({ outcome: 'invalidated', reason: 'invalid_handle' }));
    }
    if (operation.inFlight) return operation.inFlight;
    if (!operation.settled) {
      return Promise.resolve(Object.freeze({ outcome: 'rejected', reason: 'reconciliation_not_available' }));
    }
    if (operation.settled.outcome !== 'outcome_unknown') return Promise.resolve(operation.settled);
    const pending = this.executeReconcile(operation, signal);
    operation.inFlight = pending;
    const clearFlight = () => { if (operation.inFlight === pending) operation.inFlight = undefined; };
    void pending.then(clearFlight, clearFlight);
    return pending;
  }

  private commandService(): Promise<CommandService> {
    return this.service ??= Promise.resolve(this.createService());
  }

  private async executeSubmit(operation: Operation, signal?: AbortSignal): Promise<StartTravelControllerResult> {
    try {
      const result = await (await this.commandService()).submit(operation.attempt, signal);
      this.scope.clearFresh(operation.attempt.pickupId);
      void result;
      return operation.settled = Object.freeze({ outcome: 'applied' });
    } catch (error) {
      if (error instanceof StartTravelOutcomeUnknownError) {
        return operation.settled = Object.freeze({ outcome: 'outcome_unknown' });
      }
      if (error instanceof StartTravelRejectedError) {
        this.scope.clearFresh(operation.attempt.pickupId);
        return operation.settled = Object.freeze({ outcome: 'rejected', reason: error.reason });
      }
      if (error instanceof StartTravelContractError) {
        this.scope.clearFresh(operation.attempt.pickupId);
        return operation.settled = Object.freeze({ outcome: 'rejected', reason: 'malformed_response' });
      }
      if (error instanceof StartTravelAttemptInvalidError) {
        this.scope.clearFresh(operation.attempt.pickupId);
        return operation.settled = Object.freeze({ outcome: 'invalidated', reason: 'scope_changed' });
      }
      if (error instanceof PublicApiError) {
        const authorityLost = error.status === 401 || error.status === 403 || error.status === 404 ||
          error.kind === 'authentication_required' || error.kind === 'session_expired' ||
          error.kind === 'access_denied' || error.kind === 'not_found';
        if (authorityLost) {
          this.scope.clearFresh(operation.attempt.pickupId);
          return operation.settled = Object.freeze({ outcome: 'invalidated', reason: 'authority_lost' });
        }
        if (error.kind === 'malformed_response') {
          this.scope.clearFresh(operation.attempt.pickupId);
          return operation.settled = Object.freeze({ outcome: 'rejected', reason: 'malformed_response' });
        }
        if (error.status !== undefined && error.status >= 400 && error.status < 500) {
          this.scope.clearFresh(operation.attempt.pickupId);
          return operation.settled = Object.freeze({ outcome: 'rejected', reason: 'refresh_required' });
        }
      }
      throw error;
    }
  }

  private async executeReconcile(operation: Operation, signal?: AbortSignal): Promise<StartTravelControllerResult> {
    const reconciled = await (await this.commandService()).reconcile(operation.attempt, signal);
    if (reconciled.outcome === 'retry_same_attempt') {
      return operation.settled = Object.freeze({ outcome: 'retry_same_attempt' });
    }
    this.scope.clearFresh(operation.attempt.pickupId);
    if (reconciled.outcome === 'already_applied') {
      return operation.settled = Object.freeze({ outcome: 'applied' });
    }
    return operation.settled = Object.freeze({ outcome: 'invalidated', reason: reconciled.reason });
  }
}
