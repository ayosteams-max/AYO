import assert from 'node:assert/strict';
import test from 'node:test';

import type { AuthenticatedSession } from '../domain/auth-session.ts';
import { AuthenticatedReadTransport } from '../services/authenticated-read-transport.ts';
import { boundedFetch } from '../services/api-foundation.ts';
import type { SessionManager } from '../services/session-manager.ts';

const session: AuthenticatedSession = { identityId: '11111111-1111-4111-8111-111111111111', sessionId: '22222222-2222-4222-8222-222222222222', identityKind: 'rider', accessToken: 'a'.repeat(64), accessExpiresAt: '2026-08-06T01:00:00Z', refreshToken: 'r'.repeat(64), refreshExpiresAt: '2026-08-07T00:00:00Z' };

test('authenticated GET attaches current token and parses bounded JSON', async () => {
  let authorization = ''; const sessions = { accessToken: async () => session.accessToken } as SessionManager;
  const transport = new AuthenticatedReadTransport('https://api.ayo.example', sessions, async (_input, init) => { authorization = String((init?.headers as Record<string, string>).Authorization); return new Response('{"state":"ready"}', { status: 200 }); });
  assert.deepEqual(await transport.get('/api/mobile/status'), { state: 'ready' }); assert.equal(authorization, `Bearer ${session.accessToken}`);
});
test('missing session fails before network access', async () => {
  let calls = 0; const sessions = { accessToken: async () => { throw new Error('authentication_required'); } } as unknown as SessionManager;
  await assert.rejects(new AuthenticatedReadTransport('https://api.ayo.example', sessions, async () => { calls += 1; return new Response(); }).get('/status'), /authentication_required/); assert.equal(calls, 0);
});
test('one 401 refresh retry is allowed and never loops', async () => {
  let calls = 0; const sessions = { accessToken: async () => session.accessToken, forceRefresh: async () => ({ ...session, accessToken: 'b'.repeat(64) }) } as SessionManager;
  const transport = new AuthenticatedReadTransport('https://api.ayo.example', sessions, async () => { calls += 1; return new Response(calls === 1 ? '{}' : '{"ok":true}', { status: calls === 1 ? 401 : 200 }); });
  assert.deepEqual(await transport.get('/status'), { ok: true }); assert.equal(calls, 2);
});
test('second 401 returns a bounded error', async () => {
  let calls = 0; const sessions = { accessToken: async () => session.accessToken, forceRefresh: async () => session } as SessionManager;
  const transport = new AuthenticatedReadTransport('https://api.ayo.example', sessions, async () => { calls += 1; return new Response('{"detail":{"code":"authentication_required","secret":"hidden"}}', { status: 401 }); });
  await assert.rejects(transport.get('/status'), (error: unknown) => error instanceof Error && error.message === 'authentication_required'); assert.equal(calls, 2);
});
test('malformed JSON fails safely without exposing the body', async () => {
  const sessions = { accessToken: async () => session.accessToken } as SessionManager;
  await assert.rejects(new AuthenticatedReadTransport('https://api.ayo.example', sessions, async () => new Response('private body', { status: 200 })).get('/status'), (error: unknown) => error instanceof Error && error.message === 'malformed_response');
});
test('caller cancellation and timeout are bounded', async () => {
  const sessions = { accessToken: async () => session.accessToken } as SessionManager; const controller = new AbortController(); controller.abort();
  await assert.rejects(new AuthenticatedReadTransport('https://api.ayo.example', sessions, async (_input, init) => { if (init?.signal?.aborted) throw new DOMException('aborted', 'AbortError'); return new Response(); }).get('/status', controller.signal), (error: unknown) => error instanceof Error && error.message === 'request_cancelled');
});
test('request timeout aborts a stalled request', async () => {
  await assert.rejects(boundedFetch(async (_input, init) => new Promise((_resolve, reject) => init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))), 'https://api.ayo.example', {}, 1), (error: unknown) => error instanceof Error && error.message === 'request_cancelled');
});
test('invalid and credential-bearing URLs and paths are rejected', () => {
  const sessions = {} as SessionManager;
  assert.throws(() => new AuthenticatedReadTransport('https://user:secret@api.ayo.example', sessions), /invalid_api_url/);
  const transport = new AuthenticatedReadTransport('https://api.ayo.example', sessions); void assert.rejects(transport.get('//other.example'), /invalid_api_path/);
});
