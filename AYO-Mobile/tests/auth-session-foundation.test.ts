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
