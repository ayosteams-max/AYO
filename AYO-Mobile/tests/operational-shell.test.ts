import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { operationalShellCopy } from '../localization/operational-shell.ts';
const directory = dirname(fileURLToPath(import.meta.url));

test('English and Amharic operational keys match and never fall back to raw keys', () => {
  assert.deepEqual(Object.keys(operationalShellCopy.en).sort(), Object.keys(operationalShellCopy.am).sort());
  for (const locale of ['en', 'am'] as const) for (const text of Object.values(operationalShellCopy[locale])) assert.ok(text.trim().length > 0);
});

test('shell uses centralized copy, textual availability and accessible controls', async () => {
  const source = await readFile(resolve(directory, '../components/operational-shell.tsx'), 'utf8');
  assert.match(source, /operationalShellCopy\[locale\]/);
  assert.match(source, /accessibilityLiveRegion/);
  assert.match(source, /accessibilityState=\{\{ disabled \}\}/);
  assert.match(source, /minHeight: 48/);
  assert.doesNotMatch(source, /pickupId\}|merchantId\}|identityId|permission/);
});

test('destination search remains present and is guarded by returned personal context', async () => {
  const home = await readFile(resolve(directory, '../app/(tabs)/index.tsx'), 'utf8');
  const destination = await readFile(resolve(directory, '../app/destination-search.tsx'), 'utf8');
  assert.match(home, /<Link href="\/destination-search" asChild>/);
  assert.match(home, /accessibilityLabel="Choose destination"/);
  assert.match(destination, /operational\.selected\?\.kind !== 'personal'/);
});

test('shell contains no command, scanner, location, notification or raw-token integration', async () => {
  const paths = ['../components/operational-shell.tsx', '../contexts/operational-context.tsx', '../services/mobile-context.ts'];
  const source = (await Promise.all(paths.map((path) => readFile(resolve(directory, path), 'utf8')))).join('\n');
  assert.doesNotMatch(source, /accessToken|refreshToken|expo-camera|expo-location|notification|barcode|qrcode|offline queue/i);
  assert.doesNotMatch(source, /\.(post|patch|put|delete)\(/);
});
