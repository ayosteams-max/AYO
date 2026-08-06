import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Pressable, Text, View } from 'react-native';

import { IdentitySessionProvider, type IdentitySessionServices, useIdentitySession } from '@/contexts/identity-session';
import { type AuthenticatedSession } from '@/domain/auth-session';
import { type Credentials, AuthenticationApi } from '@/services/authentication-api';
import { type CredentialStore, SecureSessionVault } from '@/services/secure-session';
import { SessionManager } from '@/services/session-manager';

const credentials: Credentials = { contactKind: 'email', contact: 'person@example.test', password: 'synthetic-password' };
const originalSession: AuthenticatedSession = {
  identityId: '11111111-1111-4111-8111-111111111111',
  sessionId: '22222222-2222-4222-8222-222222222222',
  identityKind: 'rider',
  accessToken: 'a'.repeat(64),
  accessExpiresAt: '2099-01-01T01:00:00Z',
  refreshToken: 'r'.repeat(64),
  refreshExpiresAt: '2099-01-02T00:00:00Z',
};
const nextSession: AuthenticatedSession = {
  ...originalSession,
  identityId: '33333333-3333-4333-8333-333333333333',
  sessionId: '44444444-4444-4444-8444-444444444444',
  accessToken: 'b'.repeat(64),
  refreshToken: 's'.repeat(64),
};

class MemoryStore implements CredentialStore {
  value: string | null = null;
  failRemove = false;
  removeGate?: Promise<void>;
  removeStarted?: () => void;
  async get() { return this.value; }
  async set(_key: string, value: string) { this.value = value; }
  async remove() {
    this.removeStarted?.();
    if (this.removeGate) await this.removeGate;
    if (this.failRemove) throw new Error('secure_storage_unavailable');
    this.value = null;
  }
}

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((settle, fail) => { resolve = settle; reject = fail; });
  return { promise, resolve, reject };
}

type ControlledApi = Readonly<{
  api: AuthenticationApi;
  signInStarted: Promise<void>;
  resolveSignIn(session: AuthenticatedSession): void;
  rejectSignOut(error: Error): void;
  resolveSignOut(): void;
}>;

function controlledApi(options: { holdSignIn?: boolean; holdSignOut?: boolean } = {}): ControlledApi {
  const signIn = deferred<AuthenticatedSession>();
  const signInStarted = deferred<void>();
  const signOut = deferred<void>();
  const api = {
    activation: async () => ({ activated: true }),
    signIn: async () => {
      signInStarted.resolve();
      return options.holdSignIn ? signIn.promise : nextSession;
    },
    register: async () => nextSession,
    signOut: async () => options.holdSignOut ? signOut.promise : undefined,
  } as unknown as AuthenticationApi;
  return {
    api,
    signInStarted: signInStarted.promise,
    resolveSignIn: signIn.resolve,
    rejectSignOut: signOut.reject,
    resolveSignOut: () => signOut.resolve(),
  };
}

const contextOperations: Promise<void>[] = [];

function SessionConsumer() {
  const session = useIdentitySession();
  return (
    <View>
      <Text testID="session-status">{session.status}</Text>
      {session.identity ? <Text testID="authenticated-identity">{session.identity.identityId}</Text> : null}
      {session.error ? <Text testID="session-error">{session.error}</Text> : null}
      <Pressable testID="sign-out" onPress={() => { contextOperations.push(session.signOut()); }}>
        <Text>Sign out</Text>
      </Pressable>
      <Pressable testID="sign-in" onPress={() => { contextOperations.push(session.signIn(credentials)); }}>
        <Text>Sign in</Text>
      </Pressable>
    </View>
  );
}

async function mount(options: { initialSession?: AuthenticatedSession; holdSignIn?: boolean; holdSignOut?: boolean; holdRemove?: boolean; failRemove?: boolean } = {}) {
  contextOperations.length = 0;
  const store = new MemoryStore();
  const vault = new SecureSessionVault(store);
  if (options.initialSession) await vault.save(options.initialSession);
  store.failRemove = options.failRemove ?? false;
  const remove = deferred<void>();
  const removeStarted = deferred<void>();
  if (options.holdRemove) {
    store.removeGate = remove.promise;
    store.removeStarted = () => removeStarted.resolve();
  }
  const controlled = controlledApi(options);
  const manager = new SessionManager(vault, controlled.api);
  const services: IdentitySessionServices = { api: Promise.resolve(controlled.api), manager: Promise.resolve(manager) };
  await render(<IdentitySessionProvider services={services}><SessionConsumer /></IdentitySessionProvider>);
  await waitFor(() => expect(screen.getByTestId('session-status').props.children).not.toBe('restoring'));
  return { controlled, store, removeStarted: removeStarted.promise, releaseRemove: () => remove.resolve() };
}

function expectSignedOut() {
  expect(screen.getByTestId('session-status').props.children).toBe('signed_out');
  expect(screen.queryByTestId('authenticated-identity')).toBeNull();
}

test('real provider publishes signed out while manager revocation remains pending', async () => {
  const { controlled } = await mount({ initialSession: originalSession, holdSignOut: true });
  expect(screen.getByTestId('authenticated-identity').props.children).toBe(originalSession.identityId);
  await fireEvent.press(screen.getByTestId('sign-out'));
  await waitFor(expectSignedOut);
  let settled = false;
  void contextOperations[0].then(() => { settled = true; });
  await act(async () => { await Promise.resolve(); });
  expect(settled).toBe(false);
  await act(async () => { controlled.resolveSignOut(); await contextOperations[0]; });
  expectSignedOut();
});

test('real provider keeps remote-revocation failure signed out', async () => {
  const { controlled } = await mount({ initialSession: originalSession, holdSignOut: true });
  await fireEvent.press(screen.getByTestId('sign-out'));
  await waitFor(expectSignedOut);
  await act(async () => { controlled.rejectSignOut(new Error('offline')); await contextOperations[0]; });
  expectSignedOut();
  expect(screen.getByTestId('session-error').props.children).toBe('remote_sign_out_incomplete');
});

test('real provider represents local-clear failure without restoring identity', async () => {
  const { removeStarted, releaseRemove } = await mount({ initialSession: originalSession, holdRemove: true, failRemove: true });
  await fireEvent.press(screen.getByTestId('sign-out'));
  await removeStarted;
  await waitFor(expectSignedOut);
  await act(async () => { releaseRemove(); await contextOperations[0]; });
  expectSignedOut();
  expect(screen.getByTestId('session-error').props.children).toBe('secure_storage_unavailable');
});

test('stale authentication completion cannot republish through the real provider', async () => {
  const { controlled } = await mount({ holdSignIn: true });
  await fireEvent.press(screen.getByTestId('sign-in'));
  await controlled.signInStarted;
  await fireEvent.press(screen.getByTestId('sign-out'));
  await waitFor(expectSignedOut);
  await act(async () => { controlled.resolveSignIn(originalSession); await Promise.all(contextOperations); });
  expectSignedOut();
});

test('new authentication after sign-out publishes the new bounded identity', async () => {
  const { controlled } = await mount({ initialSession: originalSession, holdSignIn: true });
  await fireEvent.press(screen.getByTestId('sign-out'));
  await act(async () => { await contextOperations[0]; });
  expectSignedOut();
  await fireEvent.press(screen.getByTestId('sign-in'));
  await controlled.signInStarted;
  await act(async () => { controlled.resolveSignIn(nextSession); await contextOperations[1]; });
  expect(screen.getByTestId('session-status').props.children).toBe('authenticated');
  expect(screen.getByTestId('authenticated-identity').props.children).toBe(nextSession.identityId);
});

test('repeated real-provider sign-out settles without authenticated flicker', async () => {
  const { controlled } = await mount({ initialSession: originalSession, holdSignOut: true });
  await fireEvent.press(screen.getByTestId('sign-out'));
  await fireEvent.press(screen.getByTestId('sign-out'));
  await waitFor(expectSignedOut);
  expect(contextOperations).toHaveLength(2);
  await act(async () => { controlled.resolveSignOut(); await Promise.all(contextOperations); });
  expectSignedOut();
});
