import type { AuthenticatedSession } from '../domain/auth-session.ts';
import type { AuthenticationApi } from './authentication-api.ts';
import type { SecureSessionVault } from './secure-session.ts';

const MARGIN_MS = 30_000;
export class SessionManager {
  private refreshFlight?: Promise<AuthenticatedSession | undefined>;
  private readonly vault: SecureSessionVault;
  private readonly api: AuthenticationApi;
  private readonly now: () => number;
  constructor(vault: SecureSessionVault, api: AuthenticationApi, now: () => number = Date.now) { this.vault = vault; this.api = api; this.now = now; }
  establish(session: AuthenticatedSession) { return this.vault.save(session); }
  async restore() { const session = await this.vault.load(); return session ? this.ensureFresh(session) : undefined; }
  async accessToken() { const session = await this.restore(); if (!session) throw new Error('authentication_required'); return session.accessToken; }
  async forceRefresh(expectedToken?: string) {
    const current = await this.vault.load();
    if (!current) return undefined;
    if (expectedToken && current.accessToken !== expectedToken) return current;
    return this.refresh(current);
  }
  async signOut() {
    const session = await this.vault.load();
    let remoteError: unknown;
    try { if (session) await this.api.signOut(session.accessToken); } catch (error) { remoteError = error; }
    await this.vault.clear();
    if (remoteError) throw new Error('remote_sign_out_incomplete', { cause: remoteError });
  }
  private ensureFresh(session: AuthenticatedSession) {
    return Date.parse(session.accessExpiresAt) > this.now() + MARGIN_MS ? Promise.resolve(session) : this.refresh(session);
  }
  private refresh(session: AuthenticatedSession) {
    if (!this.refreshFlight) this.refreshFlight = this.refreshOnce(session).finally(() => { this.refreshFlight = undefined; });
    return this.refreshFlight;
  }
  private async refreshOnce(session: AuthenticatedSession) {
    try { const refreshed = await this.api.refresh(session.refreshToken); await this.vault.save(refreshed); return refreshed; }
    catch { await this.vault.clear(); return undefined; }
  }
}
