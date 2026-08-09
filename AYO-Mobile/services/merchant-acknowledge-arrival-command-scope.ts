import {
  createMerchantAcknowledgeArrivalAttempt,
  merchantAcknowledgeArrivalAttemptMatchesScope,
  type MerchantAcknowledgeArrivalAttempt,
  type MerchantAcknowledgeArrivalCommandScope as MerchantAcknowledgeArrivalScopeValue,
  type MerchantAcknowledgeArrivalReconciliation,
} from '../domain/merchant-acknowledge-arrival-command.ts';
import type { MerchantCourierPickupSnapshot } from '../domain/merchant-courier-pickup-status.ts';

type CommandIdentitySnapshot = Readonly<{
  identityId: string;
  sessionId: string;
  identityGeneration: number;
}>;

type MerchantPickupContextSnapshot = Readonly<{
  merchantId: string;
  orderId: string;
  pickupId: string;
  contextGeneration: number;
  identityContinuity: Readonly<{ isCurrent(): boolean }>;
}>;

type IdentityReader = () => CommandIdentitySnapshot | undefined;
type ContextReader = () => MerchantPickupContextSnapshot | undefined;
type AttemptFactory = (scope: MerchantAcknowledgeArrivalScopeValue) => MerchantAcknowledgeArrivalAttempt;
type FreshEvidence = Readonly<{
  identityId: string;
  sessionId: string;
  identityGeneration: number;
  contextGeneration: number;
  merchantId: string;
  orderId: string;
  pickup: MerchantCourierPickupSnapshot;
}>;

/** Opaque trusted capability. The attempt and idempotency key remain private. */
export type MerchantAcknowledgeArrivalAttemptHandle = Readonly<{ isCurrent(): boolean }>;

/**
 * Trusted publication and command-custody boundary for one merchant Pickup context.
 * Presentation code must not receive this writer; a future shell/provider owns it.
 */
export class MerchantAcknowledgeArrivalCommandScope {
  private readonly readIdentity: IdentityReader;
  private readonly readContext: ContextReader;
  private readonly createAttempt: AttemptFactory;
  private readonly attempts = new WeakMap<MerchantAcknowledgeArrivalAttemptHandle, MerchantAcknowledgeArrivalAttempt>();
  private freshEvidence?: FreshEvidence;
  private providerLifetimeActive = true;
  private retired = false;

  constructor(
    readIdentity: IdentityReader,
    readContext: ContextReader,
    createAttempt: AttemptFactory = createMerchantAcknowledgeArrivalAttempt,
  ) {
    this.readIdentity = readIdentity;
    this.readContext = readContext;
    this.createAttempt = createAttempt;
  }

  retainProviderLifetime(): void {
    if (!this.retired) this.providerLifetimeActive = true;
  }

  releaseProviderLifetime(): void {
    this.providerLifetimeActive = false;
    this.freshEvidence = undefined;
  }

  retire(): void {
    this.retired = true;
    this.providerLifetimeActive = false;
    this.freshEvidence = undefined;
  }

  publishFresh(merchantId: string, orderId: string, pickup: MerchantCourierPickupSnapshot): void {
    if (!this.lifetimeCurrent()) return;
    const identity = this.readIdentity();
    const context = this.readContext();
    if (!identity || !context || !context.identityContinuity.isCurrent() ||
      context.merchantId.toLowerCase() !== merchantId.toLowerCase() ||
      context.orderId.toLowerCase() !== orderId.toLowerCase() ||
      context.pickupId.toLowerCase() !== pickup.pickupId) {
      this.freshEvidence = undefined;
      return;
    }
    this.freshEvidence = Object.freeze({
      identityId: identity.identityId.toLowerCase(),
      sessionId: identity.sessionId.toLowerCase(),
      identityGeneration: identity.identityGeneration,
      contextGeneration: context.contextGeneration,
      merchantId: merchantId.toLowerCase(),
      orderId: orderId.toLowerCase(),
      pickup,
    });
  }

  clearFreshForAttempt(attempt: MerchantAcknowledgeArrivalAttempt): void {
    if (this.freshEvidenceMatchesAttempt(attempt)) this.freshEvidence = undefined;
  }

  publishRetryEvidence(
    attempt: MerchantAcknowledgeArrivalAttempt,
    value: Extract<MerchantAcknowledgeArrivalReconciliation, { outcome: 'retry_same_attempt' }>,
  ): boolean {
    const pickup = value.pickup;
    if (!this.operationIsCurrent(attempt) || pickup.pickupId !== attempt.pickupId ||
      pickup.state !== 'arrived_at_merchant' || pickup.version !== attempt.expectedVersion ||
      pickup.presentationAction !== 'acknowledge_arrival') return false;
    if (this.freshEvidence && !this.freshEvidenceMatchesAttempt(attempt)) return false;
    this.publishFresh(attempt.merchantId, attempt.orderId, pickup);
    return merchantAcknowledgeArrivalAttemptMatchesScope(attempt, this.currentScope());
  }

  createForCurrentPickup(): MerchantAcknowledgeArrivalAttemptHandle | undefined {
    const live = this.currentScope();
    if (!live) return undefined;
    const attempt = this.createAttempt(live);
    const handle = Object.freeze({ isCurrent: () => this.operationIsCurrent(attempt) });
    this.attempts.set(handle, attempt);
    return handle;
  }

  resolveForOperation(handle: MerchantAcknowledgeArrivalAttemptHandle): MerchantAcknowledgeArrivalAttempt | undefined {
    const attempt = this.lifetimeCurrent() ? this.attempts.get(handle) : undefined;
    return attempt && this.operationIsCurrent(attempt) ? attempt : undefined;
  }

  resolveForSubmit(handle: MerchantAcknowledgeArrivalAttemptHandle): MerchantAcknowledgeArrivalAttempt | undefined {
    const attempt = this.resolveForOperation(handle);
    return attempt && merchantAcknowledgeArrivalAttemptMatchesScope(attempt, this.currentScope()) ? attempt : undefined;
  }

  operationIsCurrent(attempt: MerchantAcknowledgeArrivalAttempt): boolean {
    if (!this.lifetimeCurrent()) return false;
    const identity = this.readIdentity();
    const context = this.readContext();
    return !!identity && !!context && context.identityContinuity.isCurrent() &&
      identity.identityId.toLowerCase() === attempt.identityId &&
      identity.sessionId.toLowerCase() === attempt.sessionId &&
      identity.identityGeneration === attempt.identityGeneration &&
      context.contextGeneration === attempt.contextGeneration &&
      context.merchantId.toLowerCase() === attempt.merchantId &&
      context.orderId.toLowerCase() === attempt.orderId &&
      context.pickupId.toLowerCase() === attempt.pickupId;
  }

  currentScope(): MerchantAcknowledgeArrivalScopeValue | undefined {
    if (!this.lifetimeCurrent()) return undefined;
    const identity = this.readIdentity();
    const context = this.readContext();
    const evidence = this.freshEvidence;
    if (!identity || !context || !evidence || !context.identityContinuity.isCurrent() ||
      identity.identityId.toLowerCase() !== evidence.identityId ||
      identity.sessionId.toLowerCase() !== evidence.sessionId ||
      identity.identityGeneration !== evidence.identityGeneration ||
      context.contextGeneration !== evidence.contextGeneration ||
      context.merchantId.toLowerCase() !== evidence.merchantId ||
      context.orderId.toLowerCase() !== evidence.orderId ||
      context.pickupId.toLowerCase() !== evidence.pickup.pickupId ||
      evidence.pickup.state !== 'arrived_at_merchant' ||
      evidence.pickup.presentationAction !== 'acknowledge_arrival') return undefined;
    return Object.freeze({
      identityId: identity.identityId,
      sessionId: identity.sessionId,
      identityGeneration: identity.identityGeneration,
      contextGeneration: context.contextGeneration,
      merchantId: context.merchantId,
      orderId: context.orderId,
      pickupId: context.pickupId,
      pickupVersion: evidence.pickup.version,
      presentationAction: 'acknowledge_arrival',
    });
  }

  private freshEvidenceMatchesAttempt(attempt: MerchantAcknowledgeArrivalAttempt): boolean {
    const evidence = this.freshEvidence;
    return !!evidence && evidence.identityGeneration === attempt.identityGeneration &&
      evidence.contextGeneration === attempt.contextGeneration && evidence.merchantId === attempt.merchantId &&
      evidence.orderId === attempt.orderId && evidence.pickup.pickupId === attempt.pickupId &&
      evidence.pickup.version === attempt.expectedVersion &&
      evidence.pickup.presentationAction === 'acknowledge_arrival';
  }

  private lifetimeCurrent(): boolean {
    return !this.retired && this.providerLifetimeActive;
  }
}
