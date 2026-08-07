import Constants from 'expo-constants';
import { Platform } from 'react-native';
import { createContext, type PropsWithChildren, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

import type { SessionIdentity } from '@/domain/auth-session';
import type { Credentials } from '@/services/authentication-api';
import { AuthenticationApi } from '@/services/authentication-api';
import { ExpoSecureCredentialStore } from '@/services/expo-secure-credential-store';
import { SecureSessionVault } from '@/services/secure-session';
import { SessionManager } from '@/services/session-manager';
import { AuthenticatedReadTransport } from '@/services/authenticated-read-transport';
import { CourierStartTravelCommandService, CourierStartTravelTransport } from '@/services/courier-start-travel-command';
import type { CourierStartTravelCommandScope } from '@/services/courier-start-travel-command-scope';

type SessionStatus = 'restoring' | 'signed_out' | 'verification_required' | 'authenticated';
type IdentityContextValue = Readonly<{ status: SessionStatus; identity?: SessionIdentity; error?: string; signIn(c: Credentials): Promise<void>; register(c: Credentials): Promise<void>; prepareVerification(kind: Credentials['contactKind'], contact: string): Promise<string>; completeVerification(challengeId: string, code: string): Promise<void>; retry(): Promise<void>; signOut(): Promise<void> }>;
const Context = createContext<IdentityContextValue | undefined>(undefined);
type AuthenticatedRead = (path: string, signal?: AbortSignal) => Promise<unknown>;
const AuthenticatedReadContext = createContext<AuthenticatedRead | undefined>(undefined);
export type CommandIdentitySnapshot = Readonly<{ identityId: string; sessionId: string; identityGeneration: number }>;
export type IdentityCommandRuntime = Readonly<{
  readIdentity(): CommandIdentitySnapshot | undefined;
  createStartTravelCommandService(scope: CourierStartTravelCommandScope): Promise<CourierStartTravelCommandService>;
}>;
const IdentityCommandRuntimeContext = createContext<IdentityCommandRuntime | undefined>(undefined);
const DEVICE_KEY = 'ayo.mobile.installation-id.v1';
export type IdentitySessionServices = Readonly<{ api: Promise<AuthenticationApi>; manager: Promise<SessionManager>; read?: AuthenticatedRead }>;
type IdentitySessionProviderProps = PropsWithChildren<{ services?: IdentitySessionServices }>;

function baseUrl() { const value = process.env.EXPO_PUBLIC_AYO_API_URL; if (!value) throw new Error('authentication_service_not_configured'); return value; }

export function IdentitySessionProvider({ children, services: suppliedServices }: IdentitySessionProviderProps) {
  const [status, setStatus] = useState<SessionStatus>('restoring');
  const [identity, setIdentity] = useState<SessionIdentity>();
  const [error, setError] = useState<string>();
  const generation = useRef(0);
  const commandIdentityGeneration = useRef(0);
  const commandIdentityRef = useRef<CommandIdentitySnapshot | undefined>(undefined);
  const services = useMemo(() => {
    if (suppliedServices) return suppliedServices;
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
  }, [suppliedServices]);
  const applyCommandIdentity = useCallback((session: Awaited<ReturnType<SessionManager['restore']>>) => {
    const previous = commandIdentityRef.current;
    if (session && previous?.identityId === session.identityId && previous.sessionId === session.sessionId) return;
    if (!session && !previous) return;
    commandIdentityGeneration.current += 1;
    commandIdentityRef.current = session ? Object.freeze({
      identityId: session.identityId,
      sessionId: session.sessionId,
      identityGeneration: commandIdentityGeneration.current,
    }) : undefined;
  }, []);
  const apply = useCallback((session: Awaited<ReturnType<SessionManager['restore']>>, activated = true) => {
    applyCommandIdentity(session);
    if (session) { setIdentity({ identityId: session.identityId, identityKind: session.identityKind }); setStatus(activated ? 'authenticated' : 'verification_required'); }
    else { setIdentity(undefined); setStatus('signed_out'); }
  }, [applyCommandIdentity]);
  const restore = useCallback(async () => {
    const current = ++generation.current; setError(undefined);
    try { const instance = await services.manager; const session = await instance.restore(); const activated = session ? (await (await services.api).activation(session.accessToken)).activated : false; if (current === generation.current) apply(session, activated); }
    catch (cause) { if (current === generation.current) { setError(cause instanceof Error ? cause.message : 'temporary_failure'); apply(undefined); } }
  }, [apply, services]);
  useEffect(() => { void restore(); }, [restore]);
  const authenticate = useCallback(async (mode: 'signIn' | 'register', credentials: Credentials) => {
    const current = ++generation.current; setError(undefined); applyCommandIdentity(undefined);
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
  }, [apply, applyCommandIdentity, services]);
  const verificationApi = useCallback(async () => { const session = await (await services.manager).restore(); if (!session) throw new Error('authentication_required'); return { api: await services.api, session }; }, [services]);
  const value = useMemo<IdentityContextValue>(() => ({ status, identity, error, signIn: (c) => authenticate('signIn', c), register: (c) => authenticate('register', c), prepareVerification: async (kind, contact) => { const { api, session } = await verificationApi(); return api.prepareVerification(session.accessToken, kind, contact); }, completeVerification: async (challengeId, code) => { const { api, session } = await verificationApi(); const progress = await api.completeVerification(session.accessToken, challengeId, code); apply(session, progress.activated); }, retry: restore, signOut: async () => {
    const current = ++generation.current;
    setError(undefined);
    apply(undefined);
    try { await (await services.manager).signOut(); }
    catch (cause) { if (current === generation.current) setError(cause instanceof Error ? cause.message : 'temporary_failure'); }
  } }), [apply, authenticate, error, identity, restore, services, status, verificationApi]);
  const authenticatedRead = useCallback<AuthenticatedRead>(async (path, signal) => {
    if (suppliedServices?.read) return suppliedServices.read(path, signal);
    return new AuthenticatedReadTransport(baseUrl(), await services.manager).get(path, signal);
  }, [services.manager, suppliedServices]);
  const commandRuntime = useMemo<IdentityCommandRuntime>(() => ({
    readIdentity: () => commandIdentityRef.current,
    createStartTravelCommandService: async (scope) => new CourierStartTravelCommandService(
      new CourierStartTravelTransport(baseUrl(), await services.manager),
      authenticatedRead,
      () => scope.currentScope(),
    ),
  }), [authenticatedRead, services.manager]);
  return <Context.Provider value={value}><IdentityCommandRuntimeContext.Provider value={commandRuntime}><AuthenticatedReadContext.Provider value={authenticatedRead}>{children}</AuthenticatedReadContext.Provider></IdentityCommandRuntimeContext.Provider></Context.Provider>;
}

export function useIdentitySession() { const value = useContext(Context); if (!value) throw new Error('identity_session_provider_required'); return value; }
export function useAuthenticatedRead() { const value = useContext(AuthenticatedReadContext); if (!value) throw new Error('identity_session_provider_required'); return value; }
/** Infrastructure-only capability. Ordinary presentation code must use useIdentitySession(). */
export function useIdentityCommandRuntime() { const value = useContext(IdentityCommandRuntimeContext); if (!value) throw new Error('identity_session_provider_required'); return value; }
