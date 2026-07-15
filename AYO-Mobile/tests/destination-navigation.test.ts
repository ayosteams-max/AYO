import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const testDirectory = dirname(fileURLToPath(import.meta.url));
const homePath = resolve(testDirectory, '../app/(tabs)/index.tsx');
const layoutPath = resolve(testDirectory, '../app/_layout.tsx');
const searchPath = resolve(testDirectory, '../app/destination-search.tsx');

test('the complete home destination row links to the search route', async () => {
  const home = await readFile(homePath, 'utf8');

  assert.match(home, /<Link href="\/destination-search" asChild>/);
  assert.match(home, /accessibilityLabel="Choose destination"/);
  assert.match(home, /\{destination \?\? "Where do you want to go\?"\}/);
});

test('the root stack registers the destination search route', async () => {
  const layout = await readFile(layoutPath, 'utf8');
  await assert.doesNotReject(() => readFile(searchPath, 'utf8'));
  assert.match(layout, /<Stack\.Screen name="destination-search"/);
});

test('selecting a result dismisses to home with the destination parameter', async () => {
  const search = await readFile(searchPath, 'utf8');

  assert.match(search, /router\.dismissTo\(\{ pathname: '\/\(tabs\)', params: \{ destination: destination\.name \} \}\)/);
});
