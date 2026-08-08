import { createContext, type PropsWithChildren, useContext, useLayoutEffect, useMemo } from 'react';

import { useCourierCommandContext } from '@/contexts/operational-context';
import type { CourierHandoffSnapshot } from '@/domain/courier-handoff-status';
import type { CourierMarkArrivedCommandService } from '@/services/courier-mark-arrived-command';
import { CourierMarkArrivedCommandScope } from '@/services/courier-mark-arrived-command-scope';
import { CourierMarkArrivedController } from '@/services/courier-mark-arrived-controller';

type TrustedIdentityCommandRuntime = Readonly<{
  readIdentity(): Readonly<{ identityId: string; sessionId: string; identityGeneration: number }> | undefined;
  createMarkArrivedCommandService(scope: CourierMarkArrivedCommandScope): Promise<CourierMarkArrivedCommandService>;
}>;
type TrustedEvidence = Readonly<{ publishFresh(pickupId: string, snapshot: CourierHandoffSnapshot): void; clearFresh(pickupId: string): void }>;
const EvidenceContext = createContext<TrustedEvidence | undefined>(undefined);

/** Infrastructure-only owner. It deliberately exports no command capability to descendants. */
export function CourierMarkArrivedCommandInfrastructureProvider({ children, identity }: PropsWithChildren<{ identity: TrustedIdentityCommandRuntime }>) {
  const courier = useCourierCommandContext();
  const scope = useMemo(() => new CourierMarkArrivedCommandScope(identity.readIdentity, courier.readCourierContext), [courier.readCourierContext, identity.readIdentity]);
  // Controller construction stays lazy with respect to privileged service construction.
  const controller = useMemo(() => new CourierMarkArrivedController(scope, () => identity.createMarkArrivedCommandService(scope)), [identity, scope]);
  void controller;
  useLayoutEffect(() => { scope.retainProviderLifetime(); return () => scope.releaseProviderLifetime(); }, [scope]);
  const evidence = useMemo<TrustedEvidence>(() => Object.freeze({
    publishFresh: (pickupId, snapshot) => scope.publishFresh(pickupId, snapshot),
    clearFresh: (pickupId) => scope.clearFresh(pickupId),
  }), [scope]);
  return <EvidenceContext.Provider value={evidence}>{children}</EvidenceContext.Provider>;
}

/** Private trusted-composition bridge; ordinary presentation is never given this writer. */
export function useTrustedMarkArrivedEvidence(): TrustedEvidence | undefined { return useContext(EvidenceContext); }
