import * as SecureStore from 'expo-secure-store';
import type { CredentialStore } from '@/services/secure-session';

const options: SecureStore.SecureStoreOptions = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY, keychainService: 'ayo.mobile.auth.v1' };
export class ExpoSecureCredentialStore implements CredentialStore {
  private async requireAvailable() { if (!(await SecureStore.isAvailableAsync())) throw new Error('secure_storage_unavailable'); }
  async get(key: string) { await this.requireAvailable(); return SecureStore.getItemAsync(key, options); }
  async set(key: string, value: string) { await this.requireAvailable(); await SecureStore.setItemAsync(key, value, options); }
  async remove(key: string) { await this.requireAvailable(); await SecureStore.deleteItemAsync(key, options); }
}
