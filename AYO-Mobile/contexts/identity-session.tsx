import Constants from 'expo-constants';
import { Platform } from 'react-native';
import { createContext, type PropsWithChildren, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

import type { SessionIdentity } from '@/domain/auth-session';
import type { Credentials } from '@/services/authentication-api';
import { AuthenticationApi } from '@/services/authentication-api';
import { ExpoSecureCredentialStore } from '@/services/expo-secure-credential-store';
import { SecureSessionVault } from '@/services/secure-session';
import { SessionManager } from '@/services/session-manager';

type SessionStatus = 'restoring' | 'signed_out' | 'verification_required' | 'authenticated';
type IdentityContextValue = Readonly<{ status: SessionStatus; identity?: SessionIdentity; error?: string; signIn(c: Credentials): Promise<void>; register(c: Credentials): Promise<void>; prepareVerification(kind: Credentials['contactKind'], contact: string): Promise<string>; completeVerification(challengeId: string, code: string): Promise<void>; retry(): Promise<void>; signOut(): Promise<void> }>;
const Context = createContext<IdentityContextValue | undefined>(undefined);
const DEVICE_KEY = 'ayo.mobile.installation-id.v1';

function baseUrl() { const value = process.env.EXPO_PUBLIC_AYO_API_URL; if (!value) throw new Error('authentication_service_not_configured'); return value; }

export function IdentitySessionProvider({ children }: PropsWithChildren) {
  const [status, setStatus] = useState<SessionStatus>('restoring');
  const [identity, setIdentity] = useState<SessionIdentity>();
  const [error, setError] = useState<string>();
  const generation = useRef(0);
  const services = useMemo(() => {
    const store = new ExpoSecureCredentialStore();
    const vault = new SecureSessionVault(store);
    const device = async () => {
      let deviceId = await store.get(DEVICE_KEY);
      if (!deviceId) { if (!globalThis.crypto?.randomUUID) throw new Error('secure_device_identity_unavailable'); deviceId = globalThis.crypto.randomUUID(); await store.set(DEVICE_KEY, deviceId); }
      return { deviceId, operatingSystemFamily: Platform.OS, applicationVersion: Constants.expoConfig?.version ?? 'unknown' };
    };
    const api = device().then(context => new AuthenticationApi(baseUrl(), context));
    const manager = api.then(client => new SessionManager(vault, client));
    return { api, manager };
  }, []);
  const apply = useCallback((session: Awaited<ReturnType<SessionManager['restore']>>, activated = true) => {
    if (session) { setIdentity({ identityId: session.identityId, identityKind: session.identityKind }); setStatus(activated ? 'authenticated' : 'verification_required'); }
    else { setIdentity(undefined); setStatus('signed_out'); }
  }, []);
  const restore = useCallback(async () => {
    const current = ++generation.current; setError(undefined);
    try { const instance = await services.manager; const session = await instance.restore(); const activated = session ? (await (await services.api).activation(session.accessToken)).activated : false; if (current === generation.current) apply(session, activated); }
    catch (cause) { if (current === generation.current) { setError(cause instanceof Error ? cause.message : 'temporary_failure'); apply(undefined); } }
  }, [apply, services]);
  useEffect(() => { void restore(); }, [restore]);
  const authenticate = useCallback(async (mode: 'signIn' | 'register', credentials: Credentials) => {
    const current = ++generation.current; setError(undefined);
    try {
      const [api, manager] = await Promise.all([services.api, services.manager]);
      if (current !== generation.current) return;
      const operation = manager.beginAuthentication();
      const session = await api[mode](credentials);
      const activated = (await api.activation(session.accessToken)).activated;
      if (current !== generation.current || !(await manager.establish(session, operation))) return;
      if (current === generation.current) apply(session, activated);
    }
    catch (cause) { if (current === generation.current) { setError(cause instanceof Error ? cause.message : 'temporary_failure'); apply(undefined); } throw cause; }
  }, [apply, services]);
  const verificationApi = useCallback(async () => { const session = await (await services.manager).restore(); if (!session) throw new Error('authentication_required'); return { api: await services.api, session }; }, [services]);
  const value = useMemo<IdentityContextValue>(() => ({ status, identity, error, signIn: (c) => authenticate('signIn', c), register: (c) => authenticate('register', c), prepareVerification: async (kind, contact) => { const { api, session } = await verificationApi(); return api.prepareVerification(session.accessToken, kind, contact); }, completeVerification: async (challengeId, code) => { const { api, session } = await verificationApi(); const progress = await api.completeVerification(session.accessToken, challengeId, code); apply(session, progress.activated); }, retry: restore, signOut: async () => { ++generation.current; try { await (await services.manager).signOut(); } finally { apply(undefined); } } }), [apply, authenticate, error, identity, restore, services, status, verificationApi]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useIdentitySession() { const value = useContext(Context); if (!value) throw new Error('identity_session_provider_required'); return value; }
