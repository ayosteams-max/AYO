import { createContext, type PropsWithChildren, useContext, useLayoutEffect, useMemo, useRef } from 'react';

import { CourierHandoffStatus } from '@/components/courier-handoff-status';
import { useCourierCommandContext } from '@/contexts/operational-context';
import type { CourierHandoffSnapshot } from '@/domain/courier-handoff-status';
import type { CourierMarkArrivedCommandService } from '@/services/courier-mark-arrived-command';
import { CourierMarkArrivedCommandScope } from '@/services/courier-mark-arrived-command-scope';
import { CourierMarkArrivedController } from '@/services/courier-mark-arrived-controller';
import type { MarkArrivedControllerResult } from '@/services/courier-mark-arrived-controller';
import { CourierStartTravelController, type StartTravelControllerResult } from '@/services/courier-start-travel-controller';
import { CourierStartTravelCommandScope } from '@/services/courier-start-travel-command-scope';

type TrustedIdentityCommandRuntime = Readonly<{
  readIdentity(): Readonly<{ identityId: string; sessionId: string; identityGeneration: number }> | undefined;
  createStartTravelCommandService(scope: CourierStartTravelCommandScope): Promise<import('@/services/courier-start-travel-command').CourierStartTravelCommandService>;
  createMarkArrivedCommandService(scope: CourierMarkArrivedCommandScope): Promise<CourierMarkArrivedCommandService>;
}>;

export type StartTravelPresentationCommand = Readonly<{
  canStartTravel(): boolean;
  startTravel(signal?: AbortSignal): Promise<StartTravelControllerResult>;
  reconcileStartTravel(signal?: AbortSignal): Promise<StartTravelControllerResult>;
}>;
export type MarkArrivedPresentationCommand = Readonly<{
  canMarkArrived(): boolean;
  canReconcileMarkArrived(): boolean;
  markArrived(signal?: AbortSignal): Promise<MarkArrivedControllerResult>;
  reconcileMarkArrived(signal?: AbortSignal): Promise<MarkArrivedControllerResult>;
}>;
type StartTravelEvidenceIntegration = Readonly<{
  publishFresh(pickupId: string, snapshot: CourierHandoffSnapshot, explicitRecovery: boolean): void;
  clearFresh(pickupId: string): void;
  isUnexpectedStartFailureLatched(): boolean;
}>;
type MarkArrivedEvidenceIntegration = Readonly<{
  publishFresh(pickupId: string, snapshot: CourierHandoffSnapshot, explicitRecovery: boolean): void;
  clearFresh(pickupId: string): void;
}>;

const CapabilityContext = createContext<StartTravelPresentationCommand | undefined>(undefined);
const MarkArrivedCapabilityContext = createContext<MarkArrivedPresentationCommand | undefined>(undefined);
const EvidenceContext = createContext<StartTravelEvidenceIntegration | undefined>(undefined);
// This writer context and its consumer remain file-private. Only the trusted Handoff
// composition below can publish or clear MARK_ARRIVED command evidence.
const MarkArrivedEvidenceContext = createContext<MarkArrivedEvidenceIntegration | undefined>(undefined);

export function CourierStartTravelCommandInfrastructureProvider({ children, identity }: PropsWithChildren<{ identity: TrustedIdentityCommandRuntime }>) {
  const courier = useCourierCommandContext();
  const scope = useMemo(() => new CourierStartTravelCommandScope(identity.readIdentity, courier.readCourierContext), [courier.readCourierContext, identity.readIdentity]);
  const controller = useMemo(() => new CourierStartTravelController(scope, () => identity.createStartTravelCommandService(scope)), [identity, scope]);
  const markArrivedScope = useMemo(() => new CourierMarkArrivedCommandScope(identity.readIdentity, courier.readCourierContext), [courier.readCourierContext, identity.readIdentity]);
  // Construction remains lazy with respect to privileged service construction.
  const markArrivedController = useMemo(() => new CourierMarkArrivedController(markArrivedScope, () => identity.createMarkArrivedCommandService(markArrivedScope)), [identity, markArrivedScope]);
  const unexpectedStartFailure = useRef(false);
  useLayoutEffect(() => {
    scope.retainProviderLifetime();
    return () => scope.releaseProviderLifetime();
  }, [scope]);
  useLayoutEffect(() => {
    markArrivedScope.retainProviderLifetime();
    return () => markArrivedScope.releaseProviderLifetime();
  }, [markArrivedScope]);
  const capability = useMemo<StartTravelPresentationCommand>(() => Object.freeze({
    canStartTravel: () => !unexpectedStartFailure.current && controller.isStartTravelActionable(),
    startTravel: async (signal) => {
      try {
        return await controller.startTravel(signal);
      } catch (error) {
        unexpectedStartFailure.current = true;
        throw error;
      }
    },
    reconcileStartTravel: (signal) => controller.reconcileCurrentOperation(signal),
  }), [controller]);
  const markArrivedCapability = useMemo<MarkArrivedPresentationCommand>(() => Object.freeze({
    canMarkArrived: () => markArrivedController.isMarkArrivedActionable(),
    canReconcileMarkArrived: () => markArrivedController.isReconciliationAvailable(),
    markArrived: (signal) => markArrivedController.markArrived(signal),
    reconcileMarkArrived: (signal) => markArrivedController.reconcileCurrentOperation(signal),
  }), [markArrivedController]);
  const evidence = useMemo<StartTravelEvidenceIntegration>(() => ({
    publishFresh: (pickupId, snapshot, explicitRecovery) => {
      scope.publishFresh(pickupId, snapshot);
      if (explicitRecovery) unexpectedStartFailure.current = false;
    },
    clearFresh: (pickupId) => scope.clearFresh(pickupId),
    isUnexpectedStartFailureLatched: () => unexpectedStartFailure.current,
  }), [scope]);
  const markArrivedEvidence = useMemo<MarkArrivedEvidenceIntegration>(() => Object.freeze({
    publishFresh: (pickupId, snapshot, explicitRecovery) => {
      markArrivedScope.publishFresh(pickupId, snapshot);
      if (explicitRecovery) markArrivedController.recoverUnexpectedSubmitFailure();
    },
    clearFresh: (pickupId) => markArrivedScope.clearFresh(pickupId),
  }), [markArrivedController, markArrivedScope]);
  return <CapabilityContext.Provider value={capability}><MarkArrivedCapabilityContext.Provider value={markArrivedCapability}><EvidenceContext.Provider value={evidence}><MarkArrivedEvidenceContext.Provider value={markArrivedEvidence}>{children}</MarkArrivedEvidenceContext.Provider></EvidenceContext.Provider></MarkArrivedCapabilityContext.Provider></CapabilityContext.Provider>;
}

/** Bounded future-facing action request: command custody remains in trusted infrastructure. */
export function useStartTravelCommand() {
  const value = useContext(CapabilityContext);
  if (!value) throw new Error('courier_start_travel_scope_provider_required');
  return value;
}

/** Bounded MARK_ARRIVED presentation request; all command custody remains private. */
export function useMarkArrivedCommand() {
  const value = useContext(MarkArrivedCapabilityContext);
  if (!value) throw new Error('courier_mark_arrived_scope_provider_required');
  return value;
}

/** Authenticated Handoff integration owns evidence publication; ordinary descendants receive no writer. */
export function TrustedCourierHandoffStatus({ pickupId }: { pickupId: string }) {
  const evidence = useContext(EvidenceContext);
  const markArrivedEvidence = useContext(MarkArrivedEvidenceContext);
  const command = useContext(CapabilityContext);
  const combinedEvidence = useMemo<StartTravelEvidenceIntegration | undefined>(() => evidence ? ({
    publishFresh: (currentPickupId, snapshot, explicitRecovery) => {
      evidence.publishFresh(currentPickupId, snapshot, explicitRecovery);
      markArrivedEvidence?.publishFresh(currentPickupId, snapshot, explicitRecovery);
    },
    clearFresh: (currentPickupId) => {
      evidence.clearFresh(currentPickupId);
      markArrivedEvidence?.clearFresh(currentPickupId);
    },
    isUnexpectedStartFailureLatched: evidence.isUnexpectedStartFailureLatched,
  }) : undefined, [evidence, markArrivedEvidence]);
  if (!combinedEvidence || !command) throw new Error('courier_start_travel_scope_provider_required');
  return <CourierHandoffStatus pickupId={pickupId} commandEvidence={combinedEvidence} startTravelCommand={command} />;
}
