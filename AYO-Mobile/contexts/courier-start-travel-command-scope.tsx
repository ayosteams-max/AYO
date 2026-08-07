import { createContext, type PropsWithChildren, useContext, useMemo } from 'react';

import { CourierHandoffStatus } from '@/components/courier-handoff-status';
import { useIdentityCommandRuntime } from '@/contexts/identity-session';
import { useCourierCommandContext } from '@/contexts/operational-context';
import type { CourierHandoffSnapshot } from '@/domain/courier-handoff-status';
import { CourierStartTravelCommandScope, type StartTravelAttemptHandle } from '@/services/courier-start-travel-command-scope';

type StartTravelAttemptCapability = Readonly<{
  canCreateAttempt(): boolean;
  createAttempt(): StartTravelAttemptHandle | undefined;
}>;
type StartTravelEvidenceIntegration = Readonly<{
  publishFresh(pickupId: string, snapshot: CourierHandoffSnapshot): void;
  clearFresh(pickupId: string): void;
}>;

const CapabilityContext = createContext<StartTravelAttemptCapability | undefined>(undefined);
const EvidenceContext = createContext<StartTravelEvidenceIntegration | undefined>(undefined);

export function CourierStartTravelCommandScopeProvider({ children }: PropsWithChildren) {
  const identity = useIdentityCommandRuntime();
  const courier = useCourierCommandContext();
  const scope = useMemo(() => new CourierStartTravelCommandScope(identity.readIdentity, courier.readCourierContext), [courier.readCourierContext, identity.readIdentity]);
  const capability = useMemo<StartTravelAttemptCapability>(() => ({
    canCreateAttempt: () => scope.currentScope() !== undefined,
    createAttempt: () => scope.createForCurrentPickup(),
  }), [scope]);
  const evidence = useMemo<StartTravelEvidenceIntegration>(() => ({
    publishFresh: (pickupId, snapshot) => scope.publishFresh(pickupId, snapshot),
    clearFresh: (pickupId) => scope.clearFresh(pickupId),
  }), [scope]);
  return <CapabilityContext.Provider value={capability}><EvidenceContext.Provider value={evidence}>{children}</EvidenceContext.Provider></CapabilityContext.Provider>;
}

/** Bounded future-facing capability: no session, generation, or raw scope is exposed. */
export function useStartTravelAttemptCapability() {
  const value = useContext(CapabilityContext);
  if (!value) throw new Error('courier_start_travel_scope_provider_required');
  return value;
}

/** Authenticated Handoff integration owns evidence publication; ordinary descendants receive no writer. */
export function TrustedCourierHandoffStatus({ pickupId }: { pickupId: string }) {
  const evidence = useContext(EvidenceContext);
  if (!evidence) throw new Error('courier_start_travel_scope_provider_required');
  return <CourierHandoffStatus pickupId={pickupId} commandEvidence={evidence} />;
}
