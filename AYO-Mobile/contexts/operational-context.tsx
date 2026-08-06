import { AppState } from 'react-native';
import { createContext, type PropsWithChildren, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

import { useAuthenticatedRead, useIdentitySession } from '@/contexts/identity-session';
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
}>;

const Context = createContext<OperationalContextValue | undefined>(undefined);
type OperationalContextProviderProps = PropsWithChildren<{ service?: MobileContextService }>;

export function OperationalContextProvider({ children, service: suppliedService }: OperationalContextProviderProps) {
  const session = useIdentitySession();
  const authenticatedRead = useAuthenticatedRead();
  const service = useMemo(() => suppliedService ?? new MobileContextService(authenticatedRead), [authenticatedRead, suppliedService]);
  const [status, setStatus] = useState<OperationalContextStatus>('idle');
  const [snapshot, setSnapshot] = useState<MobileContextSnapshot>();
  const [selectedKey, setSelectedKey] = useState<OperationalArea['key']>();
  const [chooserVisible, setChooserVisible] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const generation = useRef(0);
  const snapshotRef = useRef<MobileContextSnapshot | undefined>(undefined);
  const selectedKeyRef = useRef<OperationalArea['key'] | undefined>(undefined);
  const requestRef = useRef<Promise<void> | undefined>(undefined);
  const controllerRef = useRef<AbortController | undefined>(undefined);
  const signOutRef = useRef(session.signOut);

  useEffect(() => { snapshotRef.current = snapshot; }, [snapshot]);
  useEffect(() => { selectedKeyRef.current = selectedKey; }, [selectedKey]);
  useEffect(() => { signOutRef.current = session.signOut; }, [session.signOut]);
  const load = useCallback(() => {
    if (session.status !== 'authenticated') return Promise.resolve();
    if (requestRef.current) return requestRef.current;
    const current = generation.current;
    const controller = new AbortController();
    controllerRef.current = controller;
    setRefreshing(true);
    if (!snapshotRef.current) setStatus('loading');
    const request = service.load(controller.signal).then((next) => {
      if (current !== generation.current || controller.signal.aborted) return;
      requestRef.current = undefined;
      snapshotRef.current = next;
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
      if (snapshotRef.current) setStatus('stale');
      else setStatus(error instanceof MobileContextContractError ? 'malformed' : 'unavailable');
    }).finally(() => {
      if (requestRef.current === request) requestRef.current = undefined;
      if (controllerRef.current === controller) controllerRef.current = undefined;
      if (current === generation.current) setRefreshing(false);
    });
    requestRef.current = request;
    return request;
  }, [service, session.status]);

  const identityKey = session.identity?.identityId;
  useEffect(() => {
    generation.current += 1;
    controllerRef.current?.abort();
    requestRef.current = undefined;
    snapshotRef.current = undefined;
    setSnapshot(undefined);
    selectedKeyRef.current = undefined;
    setSelectedKey(undefined);
    setChooserVisible(false);
    setRefreshing(false);
    setStatus(session.status === 'authenticated' ? 'loading' : 'idle');
    if (session.status === 'authenticated') void load();
    return () => { generation.current += 1; controllerRef.current?.abort(); };
  }, [identityKey, load, session.status]);

  useEffect(() => AppState.addEventListener('change', (next) => {
    if (next === 'active' && session.status === 'authenticated') void load();
  }).remove, [load, session.status]);

  const areas = useMemo(() => snapshot ? operationalAreas(snapshot) : [], [snapshot]);
  const selected = areas.find((area) => area.key === selectedKey && area.enterable);
  const value = useMemo<OperationalContextValue>(() => ({
    status, areas, selected, chooserVisible, refreshing, refresh: load,
    selectArea: (key) => {
      if (status !== 'ready') return;
      const area = areas.find((candidate) => candidate.key === key && candidate.enterable);
      if (area) { selectedKeyRef.current = area.key; setSelectedKey(area.key); setChooserVisible(false); }
    },
    showChooser: () => setChooserVisible(true),
  }), [areas, chooserVisible, load, refreshing, selected, status]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useOperationalContext() {
  const value = useContext(Context);
  if (!value) throw new Error('operational_context_provider_required');
  return value;
}
