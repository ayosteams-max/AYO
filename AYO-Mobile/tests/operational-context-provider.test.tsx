import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { useEffect, useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import HomeScreen from '@/app/(tabs)/index';
import DestinationSearchScreen from '@/app/destination-search';
import { IdentitySessionProvider, type IdentitySessionServices, useIdentitySession } from '@/contexts/identity-session';
import { LanguageProvider } from '@/contexts/language';
import { OperationalContextProvider, useOperationalContext } from '@/contexts/operational-context';
import type { AuthenticatedSession } from '@/domain/auth-session';
import { AuthenticationApi } from '@/services/authentication-api';
import type { CredentialStore } from '@/services/secure-session';
import { SecureSessionVault } from '@/services/secure-session';
import { SessionManager } from '@/services/session-manager';
import { PublicApiError } from '@/services/api-foundation';

let mockNavigate: (href: unknown) => void = () => undefined;
jest.mock('@expo/vector-icons', () => {
  const React = jest.requireActual('react') as typeof import('react');
  const Native = jest.requireActual('react-native') as typeof import('react-native');
  return { MaterialCommunityIcons: ({ name }: { name: string }) => React.createElement(Native.Text, { accessibilityElementsHidden: true }, name) };
});
jest.mock('expo-router', () => {
  const React = jest.requireActual('react') as typeof import('react');
  const Native = jest.requireActual('react-native') as typeof import('react-native');
  return {
    Link: ({ href, children, asChild }: { href: unknown; children: React.ReactNode; asChild?: boolean }) => {
      if (!asChild || !React.isValidElement(children)) return children;
      const child = children as React.ReactElement<{ onPress?: (...args: unknown[]) => void }>;
      return React.cloneElement(child, { onPress: (...args: unknown[]) => { child.props.onPress?.(...args); mockNavigate(href); } });
    },
    Redirect: ({ href }: { href: unknown }) => React.createElement(Native.Text, { testID: 'redirect-target' }, String(href)),
    router: { back: jest.fn(), dismissTo: jest.fn() },
    useLocalSearchParams: () => ({}),
  };
});

const session: AuthenticatedSession = {
  identityId: '11111111-1111-4111-8111-111111111111', sessionId: '22222222-2222-4222-8222-222222222222', identityKind: 'rider',
  accessToken: 'a'.repeat(64), accessExpiresAt: '2099-01-01T01:00:00Z', refreshToken: 'r'.repeat(64), refreshExpiresAt: '2099-01-02T00:00:00Z',
};
const personal = { personal: { available: true }, merchants: [], courier: null };
const merchant = { personal: null, merchants: [{ merchant_id: '33333333-3333-4333-8333-333333333333', display_name: 'AYO Market', availability: 'available' }], courier: null };

class MemoryStore implements CredentialStore {
  value: string | null = null;
  async get() { return this.value; }
  async set(_key: string, value: string) { this.value = value; }
  async remove() { this.value = null; }
}

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((settle, fail) => { resolve = settle; reject = fail; });
  return { promise, resolve, reject };
}

const operations: Promise<void>[] = [];
function Consumer() {
  const identity = useIdentitySession();
  const operational = useOperationalContext();
  return <View>
    <Text testID="identity-status">{identity.status}</Text>
    <Text testID="operational-status">{operational.status}</Text>
    <Text testID="area-kinds">{operational.areas.map((area) => area.kind).join(',')}</Text>
    <Text testID="selected-area">{operational.selected?.kind ?? 'none'}</Text>
    <Text testID="refreshing">{operational.refreshing ? 'yes' : 'no'}</Text>
    <Pressable testID="sign-out" onPress={() => operations.push(identity.signOut())}><Text>sign out</Text></Pressable>
    <Pressable testID="refresh" onPress={() => operations.push(operational.refresh())}><Text>refresh</Text></Pressable>
  </View>;
}

function PersonalNavigationHarness() {
  const [route, setRoute] = useState<'home' | 'destination'>('home');
  const [target, setTarget] = useState('none');
  useEffect(() => {
    mockNavigate = (href) => {
      const next = String(href);
      setTarget(next);
      if (next === '/destination-search') setRoute('destination');
    };
    return () => { mockNavigate = () => undefined; };
  }, []);
  return <View>
    <Text testID="navigation-target">{target}</Text>
    <Pressable testID="return-home" onPress={() => setRoute('home')}><Text>Return to Personal</Text></Pressable>
    {route === 'home' ? <HomeScreen /> : <DestinationSearchScreen />}
  </View>;
}

async function mount(options: { initial?: AuthenticatedSession; reads?: Array<ReturnType<typeof deferred<unknown>>>; signOut?: Promise<void>; renderShell?: boolean } = {}) {
  operations.length = 0;
  const store = new MemoryStore();
  const vault = new SecureSessionVault(store);
  if (options.initial) await vault.save(options.initial);
  const api = { activation: async () => ({ activated: true }), signOut: async () => options.signOut } as unknown as AuthenticationApi;
  const manager = new SessionManager(vault, api);
  const reads = [...(options.reads ?? [])];
  let readCount = 0;
  const services: IdentitySessionServices = {
    api: Promise.resolve(api), manager: Promise.resolve(manager),
    read: async () => { readCount += 1; const next = reads.shift(); if (!next) throw new Error('unexpected_context_read'); return next.promise; },
  };
  await act(async () => { render(<IdentitySessionProvider services={services}><OperationalContextProvider><Consumer />{options.renderShell ? <LanguageProvider><PersonalNavigationHarness /></LanguageProvider> : null}</OperationalContextProvider></IdentitySessionProvider>); await Promise.resolve(); });
  await waitFor(() => expect(screen.getByTestId('identity-status').props.children).not.toBe('restoring'));
  return { readCount: () => readCount };
}

test('signed-out provider never fetches operational context', async () => {
  const mounted = await mount();
  expect(screen.getByTestId('operational-status').props.children).toBe('idle');
  expect(mounted.readCount()).toBe(0);
});

test('restored session loads and directly selects one server-returned context', async () => {
  const read = deferred<unknown>();
  const mounted = await mount({ initial: session, reads: [read] });
  await waitFor(() => expect(mounted.readCount()).toBe(1));
  await act(async () => { read.resolve(personal); });
  await waitFor(() => expect(screen.getByTestId('operational-status').props.children).toBe('ready'));
  expect(screen.getByTestId('area-kinds').props.children).toBe('personal');
  expect(screen.getByTestId('selected-area').props.children).toBe('personal');
});

test('sign-out clears shell before remote revocation settles and stale fetch cannot republish it', async () => {
  const initialRead = deferred<unknown>();
  const remoteSignOut = deferred<void>();
  await mount({ initial: session, reads: [initialRead], signOut: remoteSignOut.promise });
  await waitFor(() => expect(screen.getByTestId('operational-status').props.children).toBe('loading'));
  await act(async () => { fireEvent.press(screen.getByTestId('sign-out')); await Promise.resolve(); });
  await waitFor(() => expect(screen.getByTestId('identity-status').props.children).toBe('signed_out'));
  expect(screen.getByTestId('operational-status').props.children).toBe('idle');
  expect(screen.getByTestId('area-kinds').props.children).toBe('');
  initialRead.resolve(personal);
  await act(async () => { await Promise.resolve(); });
  expect(screen.getByTestId('area-kinds').props.children).toBe('');
  remoteSignOut.resolve();
  await act(async () => { await Promise.all(operations); });
});

test('refresh replaces the complete snapshot and removes the selected area', async () => {
  const first = deferred<unknown>(); const second = deferred<unknown>();
  const mounted = await mount({ initial: session, reads: [first, second] });
  await waitFor(() => expect(mounted.readCount()).toBe(1));
  await act(async () => { first.resolve(personal); });
  await waitFor(() => expect(screen.getByTestId('selected-area').props.children).toBe('personal'));
  await waitFor(() => expect(screen.getByTestId('refreshing').props.children).toBe('no'));
  await act(async () => { fireEvent.press(screen.getByTestId('refresh')); });
  await waitFor(() => expect(mounted.readCount()).toBe(2));
  await act(async () => { second.resolve(merchant); await operations[0]; });
  expect(screen.getByTestId('area-kinds').props.children).toBe('merchant');
  expect(screen.getByTestId('selected-area').props.children).toBe('merchant');
});

test('refresh failure retains only a stale non-enterable presentation and manual refresh recovers', async () => {
  const first = deferred<unknown>(); const failed = deferred<unknown>(); const recovered = deferred<unknown>();
  const mounted = await mount({ initial: session, reads: [first, failed, recovered] });
  await waitFor(() => expect(mounted.readCount()).toBe(1));
  await act(async () => { first.resolve(personal); });
  await waitFor(() => expect(screen.getByTestId('selected-area').props.children).toBe('personal'));
  await waitFor(() => expect(screen.getByTestId('refreshing').props.children).toBe('no'));
  await act(async () => { fireEvent.press(screen.getByTestId('refresh')); });
  await waitFor(() => expect(mounted.readCount()).toBe(2));
  await act(async () => { failed.reject(new Error('offline')); await operations[0]; });
  expect(screen.getByTestId('operational-status').props.children).toBe('stale');
  await act(async () => { fireEvent.press(screen.getByTestId('refresh')); });
  await waitFor(() => expect(mounted.readCount()).toBe(3));
  await act(async () => { recovered.resolve(merchant); await operations[1]; });
  expect(screen.getByTestId('operational-status').props.children).toBe('ready');
  expect(screen.getByTestId('selected-area').props.children).toBe('merchant');
});

test('real Personal entry enforces fresh and stale destination navigation through recovery', async () => {
  const first = deferred<unknown>(); const failed = deferred<unknown>(); const recovered = deferred<unknown>(); const removed = deferred<unknown>();
  const mounted = await mount({ initial: session, reads: [first, failed, recovered, removed], renderShell: true });
  await waitFor(() => expect(mounted.readCount()).toBe(1));
  await act(async () => { first.resolve(personal); });
  await waitFor(() => expect(screen.getByLabelText('Choose destination')).toBeTruthy());
  expect(screen.queryByText('Information may be out of date')).toBeNull();

  await act(async () => { fireEvent.press(screen.getByLabelText('Choose destination')); });
  expect(screen.getByTestId('navigation-target').props.children).toBe('/destination-search');
  expect(screen.getByLabelText('Search destination')).toBeTruthy();
  await act(async () => { fireEvent.press(screen.getByTestId('return-home')); });

  await act(async () => { fireEvent.press(screen.getByTestId('refresh')); });
  await waitFor(() => expect(mounted.readCount()).toBe(2));
  await act(async () => { failed.reject(new Error('offline')); await operations[0]; });

  expect(screen.getByLabelText('Choose destination')).toBeTruthy();
  const warning = screen.getByText('Information may be out of date');
  expect(warning.props.accessibilityLiveRegion).toBe('assertive');
  expect(screen.getByLabelText('Refresh')).toBeTruthy();

  await act(async () => { fireEvent.press(screen.getByLabelText('Choose destination')); });
  expect(screen.getByTestId('navigation-target').props.children).toBe('/destination-search');
  expect(screen.getByTestId('redirect-target').props.children).toBe('/(tabs)');
  expect(screen.queryByLabelText('Search destination')).toBeNull();
  await act(async () => { fireEvent.press(screen.getByTestId('return-home')); });

  await act(async () => { fireEvent.press(screen.getByLabelText('Refresh')); });
  await waitFor(() => expect(mounted.readCount()).toBe(3));
  await act(async () => { recovered.resolve(personal); await operations[1]; });
  await waitFor(() => expect(screen.queryByText('Information may be out of date')).toBeNull());
  await act(async () => { fireEvent.press(screen.getByLabelText('Choose destination')); });
  expect(screen.getByLabelText('Search destination')).toBeTruthy();
  await act(async () => { fireEvent.press(screen.getByTestId('return-home')); });

  await act(async () => { fireEvent.press(screen.getByTestId('refresh')); });
  await waitFor(() => expect(mounted.readCount()).toBe(4));
  await act(async () => { removed.resolve(merchant); await operations[2]; });
  await waitFor(() => expect(screen.getByText('AYO Market')).toBeTruthy());
  expect(screen.queryByLabelText('Choose destination')).toBeNull();
  expect(screen.queryByText('Information may be out of date')).toBeNull();
  const rendered = JSON.stringify(screen.toJSON());
  expect(rendered).not.toContain('11111111-1111-4111-8111-111111111111');
  expect(rendered).not.toContain('33333333-3333-4333-8333-333333333333');
});

test('expired authenticated read fails closed through the existing session sign-out path', async () => {
  const read = deferred<unknown>();
  const mounted = await mount({ initial: session, reads: [read] });
  await waitFor(() => expect(mounted.readCount()).toBe(1));
  await act(async () => { read.reject(new PublicApiError('session_expired', 401)); });
  await waitFor(() => expect(screen.getByTestId('identity-status').props.children).toBe('signed_out'));
  expect(screen.getByTestId('area-kinds').props.children).toBe('');
});
