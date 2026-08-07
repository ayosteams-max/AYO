import { attemptMatchesScope, createStartTravelAttempt, type CourierCommandScope, type StartTravelAttempt } from '../domain/courier-start-travel-command.ts';
import type { CourierHandoffSnapshot } from '../domain/courier-handoff-status.ts';

type CommandIdentitySnapshot = Readonly<{ identityId: string; sessionId: string; identityGeneration: number }>;
type CourierCommandContextSnapshot = Readonly<{ pickupId: string; contextGeneration: number; identityContinuity: Readonly<{ isCurrent(): boolean }> }>;

type IdentityReader = () => CommandIdentitySnapshot | undefined;
type CourierContextReader = () => CourierCommandContextSnapshot | undefined;
type AttemptFactory = (scope: CourierCommandScope) => StartTravelAttempt;
type FreshHandoffEvidence = Readonly<{
  pickupId: string;
  identityGeneration: number;
  contextGeneration: number;
  snapshot: CourierHandoffSnapshot;
}>;
export type StartTravelAttemptHandle = Readonly<{ isCurrent(): boolean }>;

export class CourierStartTravelCommandScope {
  private readonly readIdentity: IdentityReader;
  private readonly readCourierContext: CourierContextReader;
  private readonly createAttempt: AttemptFactory;
  private readonly attempts = new WeakMap<StartTravelAttemptHandle, StartTravelAttempt>();
  private freshEvidence?: FreshHandoffEvidence;
  private retired = false;
  private providerLifetimeActive = true;

  constructor(readIdentity: IdentityReader, readCourierContext: CourierContextReader, createAttempt: AttemptFactory = createStartTravelAttempt) {
    this.readIdentity = readIdentity;
    this.readCourierContext = readCourierContext;
    this.createAttempt = createAttempt;
  }

  /** React may rehearse cleanup/setup without retiring the logical provider instance. */
  retainProviderLifetime(): void {
    if (!this.retired) this.providerLifetimeActive = true;
  }

  /** Synchronously closes the mounted-provider lease and clears its evidence. */
  releaseProviderLifetime(): void {
    this.providerLifetimeActive = false;
    this.freshEvidence = undefined;
  }

  /** Terminal provider-ownership boundary. A retired scope cannot be revived. */
  retire(): void {
    if (this.retired) return;
    this.retired = true;
    this.providerLifetimeActive = false;
    this.freshEvidence = undefined;
  }

  publishFresh(pickupId: string, snapshot: CourierHandoffSnapshot): void {
    if (this.retired || !this.providerLifetimeActive) return;
    const courier = this.readCourierContext();
    const identity = this.readIdentity();
    if (!identity || !courier || !courier.identityContinuity.isCurrent() || courier.pickupId !== pickupId.toLowerCase()) {
      this.clearFresh(pickupId);
      return;
    }
    this.freshEvidence = Object.freeze({
      pickupId: pickupId.toLowerCase(),
      identityGeneration: identity.identityGeneration,
      contextGeneration: courier.contextGeneration,
      snapshot,
    });
  }

  clearFresh(pickupId: string): void {
    if (this.freshEvidence?.pickupId === pickupId.toLowerCase()) this.freshEvidence = undefined;
  }

  createForCurrentPickup(): StartTravelAttemptHandle | undefined {
    const scope = this.currentScope();
    if (!scope) return undefined;
    const attempt = this.createAttempt(scope);
    const handle = Object.freeze({ isCurrent: () => this.attemptIsCurrent(attempt) });
    this.attempts.set(handle, attempt);
    return handle;
  }

  /** Trusted command infrastructure only; presentation receives the handle, never this scope owner. */
  resolveForTrustedUse(handle: StartTravelAttemptHandle): StartTravelAttempt | undefined {
    return this.retired || !this.providerLifetimeActive ? undefined : this.attempts.get(handle);
  }

  attemptIsCurrent(attempt: StartTravelAttempt): boolean {
    return attemptMatchesScope(attempt, this.currentScope());
  }

  currentScope(): CourierCommandScope | undefined {
    if (this.retired || !this.providerLifetimeActive) return undefined;
    const identity = this.readIdentity();
    const courier = this.readCourierContext();
    const evidence = this.freshEvidence;
    if (
      !identity || !courier || !evidence ||
      !courier.identityContinuity.isCurrent() ||
      courier.pickupId !== evidence.pickupId ||
      evidence.identityGeneration !== identity.identityGeneration ||
      evidence.contextGeneration !== courier.contextGeneration ||
      evidence.snapshot.presentationAction !== 'start_travel'
    ) return undefined;
    return Object.freeze({
      identityId: identity.identityId,
      sessionId: identity.sessionId,
      identityGeneration: identity.identityGeneration,
      contextGeneration: courier.contextGeneration,
      pickupId: courier.pickupId,
      pickupVersion: evidence.snapshot.pickupVersion,
      presentationAction: 'start_travel',
    });
  }
}
