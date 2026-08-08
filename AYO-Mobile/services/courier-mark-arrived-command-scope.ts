import { createMarkArrivedAttempt, markArrivedAttemptMatchesScope, type MarkArrivedAttempt, type MarkArrivedCommandScope } from '../domain/courier-mark-arrived-command.ts';
import type { CourierHandoffSnapshot, CourierPickupSnapshot } from '../domain/courier-handoff-status.ts';

type CommandIdentitySnapshot = Readonly<{ identityId: string; sessionId: string; identityGeneration: number }>;
type CourierCommandContextSnapshot = Readonly<{ pickupId: string; contextGeneration: number; identityContinuity: Readonly<{ isCurrent(): boolean }> }>;
type IdentityReader = () => CommandIdentitySnapshot | undefined;
type CourierContextReader = () => CourierCommandContextSnapshot | undefined;
type AttemptFactory = (scope: MarkArrivedCommandScope) => MarkArrivedAttempt;
type FreshEvidence = Readonly<{ pickupId: string; identityGeneration: number; contextGeneration: number; snapshot: CourierHandoffSnapshot }>;

export type MarkArrivedAttemptHandle = Readonly<{ isCurrent(): boolean }>;

export class CourierMarkArrivedCommandScope {
  private readonly readIdentity: IdentityReader;
  private readonly readCourierContext: CourierContextReader;
  private readonly createAttempt: AttemptFactory;
  private readonly attempts = new WeakMap<MarkArrivedAttemptHandle, MarkArrivedAttempt>();
  private freshEvidence?: FreshEvidence;
  private providerLifetimeActive = true;
  private retired = false;

  constructor(
    readIdentity: IdentityReader,
    readCourierContext: CourierContextReader,
    createAttempt: AttemptFactory = createMarkArrivedAttempt,
  ) { this.readIdentity = readIdentity; this.readCourierContext = readCourierContext; this.createAttempt = createAttempt; }

  retainProviderLifetime(): void { if (!this.retired) this.providerLifetimeActive = true; }
  releaseProviderLifetime(): void { this.providerLifetimeActive = false; this.freshEvidence = undefined; }
  retire(): void { this.retired = true; this.providerLifetimeActive = false; this.freshEvidence = undefined; }

  publishFresh(pickupId: string, snapshot: CourierHandoffSnapshot): void {
    if (!this.lifetimeCurrent()) return;
    const identity = this.readIdentity();
    const courier = this.readCourierContext();
    const normalizedPickupId = pickupId.toLowerCase();
    if (!identity || !courier || !courier.identityContinuity.isCurrent() || courier.pickupId.toLowerCase() !== normalizedPickupId) {
      this.clearFresh(pickupId); return;
    }
    this.freshEvidence = Object.freeze({ pickupId: normalizedPickupId, identityGeneration: identity.identityGeneration, contextGeneration: courier.contextGeneration, snapshot });
  }

  clearFresh(pickupId: string): void { if (this.freshEvidence?.pickupId === pickupId.toLowerCase()) this.freshEvidence = undefined; }

  /** Re-authorizes only the exact original condition proven by strict reconciliation. */
  publishRetryEvidence(attempt: MarkArrivedAttempt, pickup: CourierPickupSnapshot): boolean {
    if (!this.operationIsCurrent(attempt) || pickup.pickupId !== attempt.pickupId || pickup.state !== 'travelling_to_merchant' ||
      pickup.version !== attempt.expectedVersion || pickup.presentationAction !== 'mark_arrived') return false;
    this.publishFresh(attempt.pickupId, Object.freeze({ status: 'travelling', pickupVersion: pickup.version, updatedAt: pickup.updatedAt, presentationAction: 'mark_arrived' }));
    return markArrivedAttemptMatchesScope(attempt, this.currentScope());
  }

  createForCurrentPickup(): MarkArrivedAttemptHandle | undefined {
    const live = this.currentScope();
    if (!live) return undefined;
    const attempt = this.createAttempt(live);
    const handle = Object.freeze({ isCurrent: () => this.operationIsCurrent(attempt) });
    this.attempts.set(handle, attempt);
    return handle;
  }

  resolveForOperation(handle: MarkArrivedAttemptHandle): MarkArrivedAttempt | undefined {
    const attempt = this.lifetimeCurrent() ? this.attempts.get(handle) : undefined;
    return attempt && this.operationIsCurrent(attempt) ? attempt : undefined;
  }

  resolveForSubmit(handle: MarkArrivedAttemptHandle): MarkArrivedAttempt | undefined {
    const attempt = this.resolveForOperation(handle);
    return attempt && markArrivedAttemptMatchesScope(attempt, this.currentScope()) ? attempt : undefined;
  }

  operationIsCurrent(attempt: MarkArrivedAttempt): boolean {
    if (!this.lifetimeCurrent()) return false;
    const identity = this.readIdentity();
    const courier = this.readCourierContext();
    return !!identity && !!courier && courier.identityContinuity.isCurrent() &&
      identity.identityId.toLowerCase() === attempt.identityId && identity.sessionId.toLowerCase() === attempt.sessionId &&
      identity.identityGeneration === attempt.identityGeneration && courier.contextGeneration === attempt.contextGeneration &&
      courier.pickupId.toLowerCase() === attempt.pickupId;
  }

  currentScope(): MarkArrivedCommandScope | undefined {
    if (!this.lifetimeCurrent()) return undefined;
    const identity = this.readIdentity(); const courier = this.readCourierContext(); const evidence = this.freshEvidence;
    if (!identity || !courier || !evidence || !courier.identityContinuity.isCurrent() ||
      courier.pickupId.toLowerCase() !== evidence.pickupId || evidence.identityGeneration !== identity.identityGeneration ||
      evidence.contextGeneration !== courier.contextGeneration || evidence.snapshot.presentationAction !== 'mark_arrived') return undefined;
    return Object.freeze({ identityId: identity.identityId, sessionId: identity.sessionId, identityGeneration: identity.identityGeneration,
      contextGeneration: courier.contextGeneration, pickupId: courier.pickupId, pickupVersion: evidence.snapshot.pickupVersion, presentationAction: 'mark_arrived' });
  }

  private lifetimeCurrent(): boolean { return !this.retired && this.providerLifetimeActive; }
}
