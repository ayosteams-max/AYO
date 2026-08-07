import { AppState } from 'react-native';
import { createContext, type PropsWithChildren, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

import { useAuthenticatedRead, useIdentityCommandRuntime, useIdentitySession } from '@/contexts/identity-session';
import { MobileContextContractError, operationalAreas, reconcileAreaSelection, type MobileContextSnapshot, type OperationalArea } from '@/domain/mobile-context';
import { MobileContextService } from '@/services/mobile-context';
import { PublicApiError } from '@/services/api-foundation';

export type OperationalContextStatus = 'idle' | 'loading' | 'ready' | 'empty' | 'stale' | 'unavailable' | 'malformed';
type OperationalContextValue = Readonly<{
  status: OperationalContextStatus;
  areas: readonly OperationalArea[];
  selected?: OperationalArea;
  chooserVisible: boolean;
  refreshing: boolean;
  refresh(): Promise<void>;
  selectArea(key: OperationalArea['key']): void;
  showChooser(): void;
  invalidateCourier(pickupId: string): void;
}>;

const Context = createContext<OperationalContextValue | undefined>(undefined);
export type CourierCommandContextSnapshot = Readonly<{ pickupId: string; contextGeneration: number; identityGeneration: number }>;
export type CourierCommandContextReader = Readonly<{ readCourierContext(): CourierCommandContextSnapshot | undefined }>;
const CourierCommandContext = createContext<CourierCommandContextReader | undefined>(undefined);
type OperationalContextProviderProps = PropsWithChildren<{ service?: MobileContextService }>;

export function OperationalContextProvider({ children, service: suppliedService }: OperationalContextProviderProps) {
  const session = useIdentitySession();
  const identityCommand = useIdentityCommandRuntime();
  const authenticatedRead = useAuthenticatedRead();
  const service = useMemo(() => suppliedService ?? new MobileContextService(authenticatedRead), [authenticatedRead, suppliedService]);
  const [status, setStatus] = useState<OperationalContextStatus>('idle');
  const [snapshot, setSnapshot] = useState<MobileContextSnapshot>();
  const [selectedKey, setSelectedKey] = useState<OperationalArea['key']>();
  const [chooserVisible, setChooserVisible] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const generation = useRef(0);
  const commandContextGeneration = useRef(0);
  const commandContextRef = useRef<CourierCommandContextSnapshot | undefined>(undefined);
  const lastCommandContextRef = useRef<CourierCommandContextSnapshot | undefined>(undefined);
  const snapshotRef = useRef<MobileContextSnapshot | undefined>(undefined);
  const selectedKeyRef = useRef<OperationalArea['key'] | undefined>(undefined);
  const requestRef = useRef<Promise<void> | undefined>(undefined);
  const controllerRef = useRef<AbortController | undefined>(undefined);
  const signOutRef = useRef(session.signOut);

  useEffect(() => { snapshotRef.current = snapshot; }, [snapshot]);
  useEffect(() => { selectedKeyRef.current = selectedKey; }, [selectedKey]);
  useEffect(() => { signOutRef.current = session.signOut; }, [session.signOut]);
  const applyCourierCommandContext = useCallback((pickupId?: string, identityGeneration?: number) => {
    const previous = lastCommandContextRef.current;
    if (pickupId && identityGeneration !== undefined && previous?.pickupId === pickupId && previous.identityGeneration === identityGeneration) {
      commandContextRef.current = previous;
      return;
    }
    if (!pickupId && !previous) { commandContextRef.current = undefined; return; }
    commandContextGeneration.current += 1;
    const next = pickupId && identityGeneration !== undefined ? Object.freeze({
      pickupId,
      contextGeneration: commandContextGeneration.current,
      identityGeneration,
    }) : undefined;
    lastCommandContextRef.current = next;
    commandContextRef.current = next;
  }, []);
  const load = useCallback(() => {
    if (session.status !== 'authenticated') return Promise.resolve();
    if (requestRef.current) return requestRef.current;
    const commandIdentity = identityCommand.readIdentity();
    const current = generation.current;
    const controller = new AbortController();
    controllerRef.current = controller;
    setRefreshing(true);
    if (!snapshotRef.current) setStatus('loading');
    const request = service.load(controller.signal).then((next) => {
      const latestIdentity = identityCommand.readIdentity();
      if (current !== generation.current || controller.signal.aborted || !commandIdentity || !latestIdentity || latestIdentity.identityGeneration !== commandIdentity.identityGeneration) return;
      requestRef.current = undefined;
      snapshotRef.current = next;
      applyCourierCommandContext(next.courier?.pickupId, commandIdentity.identityGeneration);
      setSnapshot(next);
      const areas = operationalAreas(next);
      const selection = reconcileAreaSelection(areas, selectedKeyRef.current);
      selectedKeyRef.current = selection.selectedKey;
      setSelectedKey(selection.selectedKey);
      setChooserVisible(selection.chooserVisible);
      setStatus(areas.length === 0 ? 'empty' : 'ready');
    }).catch((error: unknown) => {
      if (current !== generation.current || controller.signal.aborted) return;
      requestRef.current = undefined;
      if (error instanceof PublicApiError && (error.kind === 'session_expired' || error.kind === 'authentication_required')) {
        void signOutRef.current();
        return;
      }
      commandContextRef.current = undefined;
      if (snapshotRef.current) setStatus('stale');
      else setStatus(error instanceof MobileContextContractError ? 'malformed' : 'unavailable');
    }).finally(() => {
      if (requestRef.current === request) requestRef.current = undefined;
      if (controllerRef.current === controller) controllerRef.current = undefined;
      if (current === generation.current) setRefreshing(false);
    });
    requestRef.current = request;
    return request;
  }, [applyCourierCommandContext, identityCommand, service, session.status]);

  const identityKey = session.identity?.identityId;
  useEffect(() => {
    generation.current += 1;
    controllerRef.current?.abort();
    requestRef.current = undefined;
    snapshotRef.current = undefined;
    applyCourierCommandContext(undefined);
    setSnapshot(undefined);
    selectedKeyRef.current = undefined;
    setSelectedKey(undefined);
    setChooserVisible(false);
    setRefreshing(false);
    setStatus(session.status === 'authenticated' ? 'loading' : 'idle');
    if (session.status === 'authenticated') void load();
    return () => { generation.current += 1; controllerRef.current?.abort(); };
  }, [applyCourierCommandContext, identityKey, load, session.status]);

  useEffect(() => AppState.addEventListener('change', (next) => {
    if (next === 'active' && session.status === 'authenticated') void load();
  }).remove, [load, session.status]);

  const areas = useMemo(() => snapshot ? operationalAreas(snapshot) : [], [snapshot]);
  const selected = areas.find((area) => area.key === selectedKey && area.enterable);
  const invalidateCourier = useCallback((pickupId: string) => {
    const current = snapshotRef.current;
    if (!current?.courier || current.courier.pickupId !== pickupId) return;
    generation.current += 1;
    controllerRef.current?.abort();
    controllerRef.current = undefined;
    requestRef.current = undefined;
    applyCourierCommandContext(undefined);
    const next = Object.freeze({ personal: current.personal, merchants: current.merchants });
    snapshotRef.current = next;
    setSnapshot(next);
    const nextAreas = operationalAreas(next);
    const selection = reconcileAreaSelection(nextAreas, selectedKeyRef.current);
    selectedKeyRef.current = selection.selectedKey;
    setSelectedKey(selection.selectedKey);
    setChooserVisible(selection.chooserVisible);
    setRefreshing(false);
    setStatus(nextAreas.length === 0 ? 'empty' : 'ready');
  }, [applyCourierCommandContext]);
  const value = useMemo<OperationalContextValue>(() => ({
    status, areas, selected, chooserVisible, refreshing, refresh: load,
    selectArea: (key) => {
      if (status !== 'ready') return;
      const area = areas.find((candidate) => candidate.key === key && candidate.enterable);
      if (area) { selectedKeyRef.current = area.key; setSelectedKey(area.key); setChooserVisible(false); }
    },
    showChooser: () => setChooserVisible(true),
    invalidateCourier,
  }), [areas, chooserVisible, invalidateCourier, load, refreshing, selected, status]);
  const commandContext = useMemo<CourierCommandContextReader>(() => ({ readCourierContext: () => commandContextRef.current }), []);
  return <Context.Provider value={value}><CourierCommandContext.Provider value={commandContext}>{children}</CourierCommandContext.Provider></Context.Provider>;
}

/** Infrastructure-only capability. Selection state is deliberately excluded. */
export function useCourierCommandContext() {
  const value = useContext(CourierCommandContext);
  if (!value) throw new Error('operational_context_provider_required');
  return value;
}

export function useOperationalContext() {
  const value = useContext(Context);
  if (!value) throw new Error('operational_context_provider_required');
  return value;
}
