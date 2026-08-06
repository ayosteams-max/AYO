import { parseStoredSession, type AuthenticatedSession } from '../domain/auth-session.ts';

export interface CredentialStore { get(key: string): Promise<string | null>; set(key: string, value: string): Promise<void>; remove(key: string): Promise<void>; }
const SESSION_KEY = 'ayo.auth.session.v1';

export class SecureSessionVault {
  private readonly store: CredentialStore;
  private readonly now: () => number;
  constructor(store: CredentialStore, now: () => number = Date.now) { this.store = store; this.now = now; }

  async save(session: AuthenticatedSession) {
    if (Date.parse(session.refreshExpiresAt) <= this.now()) throw new Error('session_expired');
    await this.store.set(SESSION_KEY, JSON.stringify(session));
  }

  async load(): Promise<AuthenticatedSession | undefined> {
    const raw = await this.store.get(SESSION_KEY);
    if (!raw) return undefined;
    try {
      const session = parseStoredSession(JSON.parse(raw));
      if (Date.parse(session.refreshExpiresAt) <= this.now()) throw new Error('session_expired');
      return session;
    } catch {
      await this.clear();
      return undefined;
    }
  }

  clear() { return this.store.remove(SESSION_KEY); }
}
