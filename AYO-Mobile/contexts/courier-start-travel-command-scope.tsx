import { createContext, type PropsWithChildren, useContext, useLayoutEffect, useMemo } from 'react';

import { CourierHandoffStatus } from '@/components/courier-handoff-status';
import { useCourierCommandContext } from '@/contexts/operational-context';
import type { CourierHandoffSnapshot } from '@/domain/courier-handoff-status';
import { CourierStartTravelController, type StartTravelControllerResult } from '@/services/courier-start-travel-controller';
import { CourierStartTravelCommandScope } from '@/services/courier-start-travel-command-scope';

type TrustedIdentityCommandRuntime = Readonly<{
  readIdentity(): Readonly<{ identityId: string; sessionId: string; identityGeneration: number }> | undefined;
  createStartTravelCommandService(scope: CourierStartTravelCommandScope): Promise<import('@/services/courier-start-travel-command').CourierStartTravelCommandService>;
}>;

export type StartTravelPresentationCommand = Readonly<{
  canStartTravel(): boolean;
  startTravel(signal?: AbortSignal): Promise<StartTravelControllerResult>;
  reconcileStartTravel(signal?: AbortSignal): Promise<StartTravelControllerResult>;
}>;
type StartTravelEvidenceIntegration = Readonly<{
  publishFresh(pickupId: string, snapshot: CourierHandoffSnapshot): void;
  clearFresh(pickupId: string): void;
}>;

const CapabilityContext = createContext<StartTravelPresentationCommand | undefined>(undefined);
const EvidenceContext = createContext<StartTravelEvidenceIntegration | undefined>(undefined);

export function CourierStartTravelCommandInfrastructureProvider({ children, identity }: PropsWithChildren<{ identity: TrustedIdentityCommandRuntime }>) {
  const courier = useCourierCommandContext();
  const scope = useMemo(() => new CourierStartTravelCommandScope(identity.readIdentity, courier.readCourierContext), [courier.readCourierContext, identity.readIdentity]);
  const controller = useMemo(() => new CourierStartTravelController(scope, () => identity.createStartTravelCommandService(scope)), [identity, scope]);
  useLayoutEffect(() => {
    scope.retainProviderLifetime();
    return () => scope.releaseProviderLifetime();
  }, [scope]);
  const capability = useMemo<StartTravelPresentationCommand>(() => Object.freeze({
    canStartTravel: () => controller.isStartTravelActionable(),
    startTravel: (signal) => controller.startTravel(signal),
    reconcileStartTravel: (signal) => controller.reconcileCurrentOperation(signal),
  }), [controller]);
  const evidence = useMemo<StartTravelEvidenceIntegration>(() => ({
    publishFresh: (pickupId, snapshot) => scope.publishFresh(pickupId, snapshot),
    clearFresh: (pickupId) => scope.clearFresh(pickupId),
  }), [scope]);
  return <CapabilityContext.Provider value={capability}><EvidenceContext.Provider value={evidence}>{children}</EvidenceContext.Provider></CapabilityContext.Provider>;
}

/** Bounded future-facing action request: command custody remains in trusted infrastructure. */
export function useStartTravelCommand() {
  const value = useContext(CapabilityContext);
  if (!value) throw new Error('courier_start_travel_scope_provider_required');
  return value;
}

/** Authenticated Handoff integration owns evidence publication; ordinary descendants receive no writer. */
export function TrustedCourierHandoffStatus({ pickupId }: { pickupId: string }) {
  const evidence = useContext(EvidenceContext);
  const command = useContext(CapabilityContext);
  if (!evidence || !command) throw new Error('courier_start_travel_scope_provider_required');
  return <CourierHandoffStatus pickupId={pickupId} commandEvidence={evidence} startTravelCommand={command} />;
}
