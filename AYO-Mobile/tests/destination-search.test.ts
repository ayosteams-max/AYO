import assert from 'node:assert/strict';
import test from 'node:test';

import { OfflineDestinationSearchGateway } from '../services/destination-search.ts';

const gateway = new OfflineDestinationSearchGateway([
  { id: '1', name: 'Bole Airport', address: 'Bole', category: 'airport' },
  { id: '2', name: 'Home', address: 'Kazanchis', category: 'saved' },
  { id: '3', name: 'Meskel Square', address: 'Kirkos', category: 'recent' },
]);

test('search matches names and addresses without case sensitivity', async () => {
  assert.deepEqual((await gateway.search({ query: 'KIRKOS', limit: 20 })).map((item) => item.id), ['3']);
});

test('category filtering and limits are enforced', async () => {
  const results = await gateway.search({ query: '', category: 'saved', limit: 1 });
  assert.deepEqual(results.map((item) => item.id), ['2']);
});

test('an aborted request does not return stale results', async () => {
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(gateway.search({ query: '', limit: 20, signal: controller.signal }), { name: 'AbortError' });
});
