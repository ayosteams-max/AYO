import { attemptMatchesScope, createStartTravelAttempt, type CourierCommandScope, type StartTravelAttempt } from '../domain/courier-start-travel-command.ts';
import type { CourierHandoffSnapshot } from '../domain/courier-handoff-status.ts';

type CommandIdentitySnapshot = Readonly<{ identityId: string; sessionId: string; identityGeneration: number }>;
type CourierCommandContextSnapshot = Readonly<{ pickupId: string; contextGeneration: number; identityGeneration: number }>;

type IdentityReader = () => CommandIdentitySnapshot | undefined;
type CourierContextReader = () => CourierCommandContextSnapshot | undefined;
type AttemptFactory = (scope: CourierCommandScope) => StartTravelAttempt;
type FreshHandoffEvidence = Readonly<{
  pickupId: string;
  identityGeneration: number;
  contextGeneration: number;
  snapshot: CourierHandoffSnapshot;
}>;

export class CourierStartTravelCommandScope {
  private readonly readIdentity: IdentityReader;
  private readonly readCourierContext: CourierContextReader;
  private readonly createAttempt: AttemptFactory;
  private freshEvidence?: FreshHandoffEvidence;

  constructor(readIdentity: IdentityReader, readCourierContext: CourierContextReader, createAttempt: AttemptFactory = createStartTravelAttempt) {
    this.readIdentity = readIdentity;
    this.readCourierContext = readCourierContext;
    this.createAttempt = createAttempt;
  }

  publishFresh(pickupId: string, snapshot: CourierHandoffSnapshot): void {
    const courier = this.readCourierContext();
    const identity = this.readIdentity();
    if (!identity || !courier || courier.identityGeneration !== identity.identityGeneration || courier.pickupId !== pickupId.toLowerCase()) {
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

  createForCurrentPickup(): StartTravelAttempt | undefined {
    const scope = this.currentScope();
    return scope ? this.createAttempt(scope) : undefined;
  }

  attemptIsCurrent(attempt: StartTravelAttempt): boolean {
    return attemptMatchesScope(attempt, this.currentScope());
  }

  currentScope(): CourierCommandScope | undefined {
    const identity = this.readIdentity();
    const courier = this.readCourierContext();
    const evidence = this.freshEvidence;
    if (
      !identity || !courier || !evidence ||
      courier.identityGeneration !== identity.identityGeneration ||
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
