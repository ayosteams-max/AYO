import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { parseAuthenticationSession, type AuthenticatedSession } from '../domain/auth-session.ts';
import { AuthenticationApi } from '../services/authentication-api.ts';
import { SecureSessionVault, type CredentialStore } from '../services/secure-session.ts';
import { SessionManager } from '../services/session-manager.ts';

const now = Date.parse('2026-08-06T00:00:00Z');
const testDirectory = dirname(fileURLToPath(import.meta.url));
const response = { identity_id: '11111111-1111-4111-8111-111111111111', session_id: '22222222-2222-4222-8222-222222222222', identity_type: 'rider', access_token: 'a'.repeat(64), access_expires_at: '2026-08-06T01:00:00Z', refresh_token: 'r'.repeat(64), refresh_expires_at: '2026-08-07T00:00:00Z', token_type: 'Bearer', internal_permissions: ['never-persist'] };
const session = parseAuthenticationSession(response);

class MemoryStore implements CredentialStore {
  value: string | null = null; removed = 0; fail = false;
  async get() { if (this.fail) throw new Error('secure_storage_unavailable'); return this.value; }
  async set(_key: string, value: string) { if (this.fail) throw new Error('write_failed'); this.value = value; }
  async remove() { this.removed += 1; this.value = null; }
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((settle, fail) => { resolve = settle; reject = fail; });
  return { promise, resolve, reject };
}

function refreshed(marker: string): AuthenticatedSession {
  return { ...session, accessToken: marker.repeat(64), refreshToken: marker.toUpperCase().repeat(64) };
}

test('authentication parser returns only the bounded opaque session', () => {
  assert.deepEqual(Object.keys(session).sort(), ['accessExpiresAt', 'accessToken', 'identityId', 'identityKind', 'refreshExpiresAt', 'refreshToken', 'sessionId'].sort());
  assert.equal(JSON.stringify(session).includes('internal_permissions'), false);
});
test('missing token and malformed expiry fail closed', () => {
  assert.throws(() => parseAuthenticationSession({ ...response, access_token: undefined }), /malformed/);
  assert.throws(() => parseAuthenticationSession({ ...response, access_expires_at: 'tomorrow' }), /malformed/);
});
test('valid session saves, loads and serializes deterministically', async () => {
  const store = new MemoryStore(); const vault = new SecureSessionVault(store, () => now); await vault.save(session);
  assert.deepEqual(await vault.load(), session); assert.equal(store.value, JSON.stringify(session));
});
test('malformed and expired stored sessions are removed', async () => {
  const store = new MemoryStore(); const vault = new SecureSessionVault(store, () => now); store.value = '{bad'; assert.equal(await vault.load(), undefined);
  store.value = JSON.stringify({ ...session, refreshExpiresAt: '2026-08-05T00:00:00Z' }); assert.equal(await vault.load(), undefined); assert.equal(store.removed, 2);
});
test('storage failures never report authenticated success', async () => {
  const store = new MemoryStore(); store.fail = true; const vault = new SecureSessionVault(store, () => now);
  await assert.rejects(vault.save(session), /write_failed/); await assert.rejects(vault.load(), /secure_storage_unavailable/);
});
test('authentication client validates HTTPS, loopback and sanitized errors', async () => {
  assert.throws(() => new AuthenticationApi('http://api.ayo.example', { deviceId: response.identity_id, operatingSystemFamily: 'android', applicationVersion: '1' }), /secure_api/);
  assert.doesNotThrow(() => new AuthenticationApi('http://127.0.0.1:8000', { deviceId: response.identity_id, operatingSystemFamily: 'android', applicationVersion: '1' }));
  const api = new AuthenticationApi('https://api.ayo.example', { deviceId: response.identity_id, operatingSystemFamily: 'android', applicationVersion: '1' }, async () => new Response(JSON.stringify({ detail: { code: 'authentication_failed', internal: 'hidden' } }), { status: 401 }));
  await assert.rejects(api.signIn({ contactKind: 'email', contact: 'a@b.test', password: 'synthetic-password' }), (error: unknown) => error instanceof Error && error.message === 'access_denied');
});
test('authentication client parses valid response and rejects malformed response', async () => {
  const device = { deviceId: response.identity_id, operatingSystemFamily: 'android', applicationVersion: '1' };
  const valid = new AuthenticationApi('https://api.ayo.example', device, async () => new Response(JSON.stringify(response), { status: 200 }));
  assert.deepEqual(await valid.signIn({ contactKind: 'email', contact: 'a@b.test', password: 'synthetic-password' }), session);
  const invalid = new AuthenticationApi('https://api.ayo.example', device, async () => new Response('{}', { status: 200 }));
  await assert.rejects(invalid.signIn({ contactKind: 'email', contact: 'a@b.test', password: 'synthetic-password' }), /malformed/);
});
test('session restoration refreshes once and concurrent callers share the refresh', async () => {
  const store = new MemoryStore(); const expired: AuthenticatedSession = { ...session, accessExpiresAt: '2026-08-05T00:00:00Z' }; const vault = new SecureSessionVault(store, () => now); await vault.save(expired);
  let refreshes = 0; const api = { refresh: async () => { refreshes += 1; await new Promise(resolve => setTimeout(resolve, 5)); return session; }, signOut: async () => undefined } as unknown as AuthenticationApi;
  const manager = new SessionManager(vault, api, () => now); const [one, two] = await Promise.all([manager.restore(), manager.restore()]);
  assert.deepEqual(one, session); assert.deepEqual(two, session); assert.equal(refreshes, 1);
});
test('refresh completing after sign-out cannot restore credentials', async () => {
  const store = new MemoryStore(); const vault = new SecureSessionVault(store, () => now);
  store.value = JSON.stringify({ ...session, accessExpiresAt: '2026-08-05T00:00:00Z' });
  const responseGate = deferred<AuthenticatedSession>(); const started = deferred<void>();
  const api = { refresh: async () => { started.resolve(); return responseGate.promise; }, signOut: async () => undefined } as unknown as AuthenticationApi;
  const manager = new SessionManager(vault, api, () => now); const restoring = manager.restore(); await started.promise;
  await manager.signOut(); responseGate.resolve(refreshed('b'));
  assert.equal(await restoring, undefined); assert.equal(store.value, null); assert.equal(await manager.restore(), undefined);
});
test('authentication completing after sign-out is rejected before persistence', async () => {
  const store = new MemoryStore(); const vault = new SecureSessionVault(store, () => now);
  const manager = new SessionManager(vault, { signOut: async () => undefined } as unknown as AuthenticationApi, () => now);
  const operation = manager.beginAuthentication(); await manager.signOut();
  assert.equal(await manager.establish(session, operation), false); assert.equal(store.value, null); assert.equal(await manager.restore(), undefined);
});
test('sign-out during an asynchronous save clears the completed stale write', async () => {
  const writeStarted = deferred<void>(); const releaseWrite = deferred<void>();
  class BlockingStore extends MemoryStore { override async set(key: string, value: string) { writeStarted.resolve(); await releaseWrite.promise; return super.set(key, value); } }
  const store = new BlockingStore(); const vault = new SecureSessionVault(store, () => now);
  const manager = new SessionManager(vault, { signOut: async () => undefined } as unknown as AuthenticationApi, () => now);
  const operation = manager.beginAuthentication(); const saving = manager.establish(session, operation); await writeStarted.promise;
  const signingOut = manager.signOut(); releaseWrite.resolve();
  assert.equal(await saving, false); await signingOut; assert.equal(store.value, null); assert.equal(await manager.restore(), undefined);
});
test('an old refresh cannot overwrite a newer login', async () => {
  const store = new MemoryStore(); const vault = new SecureSessionVault(store, () => now);
  store.value = JSON.stringify({ ...session, accessExpiresAt: '2026-08-05T00:00:00Z' });
  const responseGate = deferred<AuthenticatedSession>(); const started = deferred<void>();
  const api = { refresh: async () => { started.resolve(); return responseGate.promise; }, signOut: async () => undefined } as unknown as AuthenticationApi;
  const manager = new SessionManager(vault, api, () => now); const oldRefresh = manager.restore(); await started.promise; await manager.signOut();
  const newSession = refreshed('c'); const operation = manager.beginAuthentication(); assert.equal(await manager.establish(newSession, operation), true);
  responseGate.resolve(refreshed('b')); assert.equal(await oldRefresh, undefined); assert.deepEqual(await vault.load(), newSession);
});
test('an old authentication cannot overwrite a newer authentication', async () => {
  const store = new MemoryStore(); const vault = new SecureSessionVault(store, () => now);
  const manager = new SessionManager(vault, { signOut: async () => undefined } as unknown as AuthenticationApi, () => now);
  const oldOperation = manager.beginAuthentication(); await manager.signOut(); const newOperation = manager.beginAuthentication();
  const newSession = refreshed('c'); assert.equal(await manager.establish(newSession, newOperation), true);
  assert.equal(await manager.establish(refreshed('b'), oldOperation), false); assert.deepEqual(await vault.load(), newSession);
});
test('sign-out invalidates every caller sharing an in-flight refresh', async () => {
  const store = new MemoryStore(); const vault = new SecureSessionVault(store, () => now);
  store.value = JSON.stringify({ ...session, accessExpiresAt: '2026-08-05T00:00:00Z' });
  const responseGate = deferred<AuthenticatedSession>(); const started = deferred<void>(); let refreshes = 0;
  const api = { refresh: async () => { refreshes += 1; started.resolve(); return responseGate.promise; }, signOut: async () => undefined } as unknown as AuthenticationApi;
  const manager = new SessionManager(vault, api, () => now); const callers = [manager.restore(), manager.restore()]; await started.promise; await manager.signOut(); responseGate.resolve(refreshed('b'));
  assert.deepEqual(await Promise.all(callers), [undefined, undefined]); assert.equal(refreshes, 1); assert.equal(store.value, null);
});
test('new authentication after sign-out persists normally', async () => {
  const store = new MemoryStore(); const vault = new SecureSessionVault(store, () => now);
  const manager = new SessionManager(vault, { signOut: async () => undefined } as unknown as AuthenticationApi, () => now);
  await manager.signOut(); const operation = manager.beginAuthentication(); assert.equal(await manager.establish(session, operation), true); assert.deepEqual(await manager.restore(), session);
});
test('invalidation during refresh, save and sign-out settles without deadlock', async () => {
  const store = new MemoryStore(); const vault = new SecureSessionVault(store, () => now);
  store.value = JSON.stringify({ ...session, accessExpiresAt: '2026-08-05T00:00:00Z' });
  const responseGate = deferred<AuthenticatedSession>(); const started = deferred<void>();
  const api = { refresh: async () => { started.resolve(); return responseGate.promise; }, signOut: async () => undefined } as unknown as AuthenticationApi;
  const manager = new SessionManager(vault, api, () => now); const refresh = manager.restore(); await started.promise; const signOut = manager.signOut(); responseGate.resolve(refreshed('b'));
  assert.deepEqual(await Promise.all([refresh, signOut]), [undefined, undefined]); assert.equal(store.value, null);
});
test('failed refresh clears authentication and cannot loop', async () => {
  const store = new MemoryStore(); const vault = new SecureSessionVault(store, () => now); await vault.save({ ...session, accessExpiresAt: '2026-08-05T00:00:00Z' });
  let refreshes = 0; const api = { refresh: async () => { refreshes += 1; throw new Error('offline'); }, signOut: async () => undefined } as unknown as AuthenticationApi;
  const manager = new SessionManager(vault, api, () => now); assert.equal(await manager.restore(), undefined); assert.equal(await manager.restore(), undefined); assert.equal(refreshes, 1);
});
test('sign-out clears local credentials even when remote revocation fails', async () => {
  const store = new MemoryStore(); const vault = new SecureSessionVault(store, () => now); await vault.save(session);
  const api = { signOut: async () => { throw new Error('offline'); } } as unknown as AuthenticationApi; const manager = new SessionManager(vault, api, () => now);
  await assert.rejects(manager.signOut(), /remote_sign_out_incomplete/); assert.equal(await vault.load(), undefined);
});
test('session code never logs tokens or raw bodies', async () => {
  const sources = await Promise.all(['../services/secure-session.ts', '../services/authentication-api.ts', '../services/session-manager.ts'].map(path => readFile(resolve(testDirectory, path), 'utf8')));
  for (const source of sources) assert.doesNotMatch(source, /console\.|JSON\.stringify\([^)]*(?:response|error)/);
});
test('provider publishes signed-out context before awaiting revocation', async () => {
  const source = await readFile(resolve(testDirectory, '../contexts/identity-session.tsx'), 'utf8');
  const signOut = source.slice(source.indexOf('signOut: async () => {'));
  const invalidate = signOut.indexOf('++generation.current'); const publish = signOut.indexOf('apply(undefined)'); const revoke = signOut.indexOf('await (await services.manager).signOut()');
  assert.ok(invalidate >= 0 && invalidate < publish && publish < revoke);
});
test('provider keeps remote-revocation failure fail-closed', async () => {
  const source = await readFile(resolve(testDirectory, '../contexts/identity-session.tsx'), 'utf8');
  const signOut = source.slice(source.indexOf('signOut: async () => {'));
  assert.match(signOut, /catch \(cause\) \{ if \(current === generation\.current\) setError\(/);
  assert.equal((signOut.match(/apply\(undefined\)/g) ?? []).length, 1);
  assert.doesNotMatch(signOut, /apply\(session/);
});
test('pending sign-out ordering is deterministic and does not await before publication', async () => {
  const completion = deferred<void>(); const events: string[] = [];
  const signOut = async () => { events.push('invalidate'); events.push('publish_signed_out'); try { await completion.promise; events.push('revoked'); } catch { events.push('bounded_error'); } };
  const pending = signOut(); assert.deepEqual(events, ['invalidate', 'publish_signed_out']); completion.resolve(); await pending; assert.deepEqual(events, ['invalidate', 'publish_signed_out', 'revoked']);
});
test('revocation or clear failure cannot restore authenticated presentation', async () => {
  const completion = deferred<void>(); const state = { status: 'authenticated', identity: 'identity', error: '' };
  const signOut = async () => { state.status = 'signed_out'; state.identity = ''; try { await completion.promise; } catch { state.error = 'bounded_failure'; } };
  const pending = signOut(); assert.deepEqual(state, { status: 'signed_out', identity: '', error: '' }); completion.reject(new Error('remote'));
  await pending; assert.deepEqual(state, { status: 'signed_out', identity: '', error: 'bounded_failure' });
});
test('local clear failure remains invalidated and rejects obsolete persistence', async () => {
  class FailingClearStore extends MemoryStore { override async remove() { throw new Error('secure_storage_unavailable'); } }
  const store = new FailingClearStore(); store.value = JSON.stringify(session); const vault = new SecureSessionVault(store, () => now);
  const manager = new SessionManager(vault, { signOut: async () => undefined } as unknown as AuthenticationApi, () => now); const obsolete = manager.beginAuthentication();
  await assert.rejects(manager.signOut(), /secure_storage_unavailable/); assert.equal(await manager.establish(refreshed('b'), obsolete), false); assert.equal(store.value, JSON.stringify(session));
});
test('stale authentication completion cannot win during pending sign-out', async () => {
  const completion = deferred<void>(); let generation = 1; const state = { status: 'authenticated', identity: 'identity' };
  const authenticationGeneration = generation; const signOut = async () => { generation += 1; state.status = 'signed_out'; state.identity = ''; await completion.promise; };
  const pending = signOut(); if (authenticationGeneration === generation) { state.status = 'authenticated'; state.identity = 'stale'; }
  assert.deepEqual(state, { status: 'signed_out', identity: '' }); completion.resolve(); await pending;
});
test('repeated pending sign-out operations settle without authenticated flicker', async () => {
  const first = deferred<void>(); const second = deferred<void>(); const state = { status: 'authenticated', identity: 'identity' }; let calls = 0;
  const signOut = async () => { state.status = 'signed_out'; state.identity = ''; await (++calls === 1 ? first.promise : second.promise); };
  const operations = [signOut(), signOut()]; assert.deepEqual(state, { status: 'signed_out', identity: '' }); second.resolve(); first.resolve(); await Promise.all(operations); assert.deepEqual(state, { status: 'signed_out', identity: '' });
});
