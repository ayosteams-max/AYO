import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { authenticationCopy } from '../localization/authentication.ts';
const testDirectory = dirname(fileURLToPath(import.meta.url));

test('English and Amharic authentication keys and placeholders match', () => {
  assert.deepEqual(Object.keys(authenticationCopy.en).sort(), Object.keys(authenticationCopy.am).sort());
  for (const locale of ['en', 'am'] as const) for (const value of Object.values(authenticationCopy[locale])) assert.ok(value.length > 0);
});
test('authentication screen uses centralized copy and accessible controls', async () => {
  const source = await readFile(resolve(testDirectory, '../app/auth.tsx'), 'utf8');
  assert.match(source, /authenticationCopy\[locale\]/); assert.match(source, /accessibilityLiveRegion="assertive"/); assert.match(source, /accessibilityRole="button"/); assert.doesNotMatch(source, /expo-camera|expo-location|custody|courier|merchant/);
});
test('provider derives platform and version and has a stable effect dependency', async () => {
  const source = await readFile(resolve(testDirectory, '../contexts/identity-session.tsx'), 'utf8');
  assert.match(source, /Platform\.OS/); assert.match(source, /Constants\.expoConfig\?\.version/); assert.match(source, /useEffect\(\(\) => \{ void restore\(\); \}, \[restore\]\)/); assert.doesNotMatch(source, /operatingSystemFamily: 'android'/);
});
test('navigation preserves destination search and adds only the account route', async () => {
  const layout = await readFile(resolve(testDirectory, '../app/_layout.tsx'), 'utf8');
  assert.match(layout, /name="destination-search"/); assert.match(layout, /name="auth"/); assert.doesNotMatch(layout, /custody|courier|merchant|commerce|delivery/);
});
