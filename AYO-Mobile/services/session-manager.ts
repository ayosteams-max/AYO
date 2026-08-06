import type { AuthenticatedSession } from '../domain/auth-session.ts';
import type { AuthenticationApi } from './authentication-api.ts';
import type { SecureSessionVault } from './secure-session.ts';

const MARGIN_MS = 30_000;
export class SessionManager {
  private refreshFlight?: Readonly<{ generation: number; promise: Promise<AuthenticatedSession | undefined> }>;
  private generation = 0;
  private credentialMutation: Promise<void> = Promise.resolve();
  private readonly vault: SecureSessionVault;
  private readonly api: AuthenticationApi;
  private readonly now: () => number;
  constructor(vault: SecureSessionVault, api: AuthenticationApi, now: () => number = Date.now) { this.vault = vault; this.api = api; this.now = now; }
  beginAuthentication() { this.generation += 1; return this.generation; }
  establish(session: AuthenticatedSession, generation = this.generation) { return this.persist(session, generation); }
  async restore() { const session = await this.vault.load(); return session ? this.ensureFresh(session) : undefined; }
  async accessToken() { const session = await this.restore(); if (!session) throw new Error('authentication_required'); return session.accessToken; }
  async forceRefresh(expectedToken?: string) {
    const current = await this.vault.load();
    if (!current) return undefined;
    if (expectedToken && current.accessToken !== expectedToken) return current;
    return this.refresh(current);
  }
  async signOut() {
    this.generation += 1;
    const session = await this.serialize(async () => { const current = await this.vault.load(); await this.vault.clear(); return current; });
    let remoteError: unknown;
    try { if (session) await this.api.signOut(session.accessToken); } catch (error) { remoteError = error; }
    if (remoteError) throw new Error('remote_sign_out_incomplete', { cause: remoteError });
  }
  private ensureFresh(session: AuthenticatedSession) {
    return Date.parse(session.accessExpiresAt) > this.now() + MARGIN_MS ? Promise.resolve(session) : this.refresh(session);
  }
  private refresh(session: AuthenticatedSession) {
    const generation = this.generation;
    if (!this.refreshFlight || this.refreshFlight.generation !== generation) {
      const promise = this.refreshOnce(session, generation).finally(() => { if (this.refreshFlight?.promise === promise) this.refreshFlight = undefined; });
      this.refreshFlight = { generation, promise };
    }
    return this.refreshFlight.promise;
  }
  private async refreshOnce(session: AuthenticatedSession, generation: number) {
    try {
      const refreshed = await this.api.refresh(session.refreshToken);
      return await this.persist(refreshed, generation) ? refreshed : undefined;
    } catch {
      if (generation === this.generation) await this.serialize(() => this.vault.clear());
      return undefined;
    }
  }
  private persist(session: AuthenticatedSession, generation: number) {
    return this.serialize(async () => {
      if (generation !== this.generation) return false;
      await this.vault.save(session);
      if (generation !== this.generation) { await this.vault.clear(); return false; }
      return true;
    });
  }
  private serialize<T>(operation: () => Promise<T>): Promise<T> {
    const result = this.credentialMutation.then(operation, operation);
    this.credentialMutation = result.then(() => undefined, () => undefined);
    return result;
  }
}
