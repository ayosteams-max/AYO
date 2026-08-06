import { parseAuthenticationSession, type AuthenticatedSession } from '../domain/auth-session.ts';
import { boundedFetch, parsePublicError, validateApiBaseUrl } from './api-foundation.ts';

export type ContactKind = 'email' | 'phone';
export type DeviceContext = Readonly<{ deviceId: string; operatingSystemFamily: string; applicationVersion: string }>;
export type Credentials = Readonly<{ contactKind: ContactKind; contact: string; password: string }>;
export type ActivationProgress = Readonly<{ activated: boolean }>;

export class AuthenticationApi {
  private readonly baseUrl: string;
  private readonly device: DeviceContext;
  private readonly request: typeof fetch;
  constructor(baseUrl: string, device: DeviceContext, request: typeof fetch = fetch) { this.baseUrl = validateApiBaseUrl(baseUrl); this.device = device; this.request = request; }
  register(credentials: Credentials, signal?: AbortSignal) { return this.exchange('/api/auth/register', credentials, signal); }
  signIn(credentials: Credentials, signal?: AbortSignal) { return this.exchange('/api/auth/sign-in', credentials, signal); }
  async refresh(refreshToken: string, signal?: AbortSignal): Promise<AuthenticatedSession> {
    return this.session('/api/auth/refresh', { refresh_token: refreshToken }, signal);
  }
  async signOut(accessToken: string, signal?: AbortSignal) {
    const response = await boundedFetch(this.request, `${this.baseUrl}/api/auth/sign-out`, { method: 'POST', headers: { Accept: 'application/json', Authorization: `Bearer ${accessToken}` }, signal });
    if (!response.ok && response.status !== 401) throw await parsePublicError(response);
  }
  async activation(accessToken: string, signal?: AbortSignal): Promise<ActivationProgress> {
    const response = await boundedFetch(this.request, `${this.baseUrl}/api/auth/activation`, { headers: { Accept: 'application/json', Authorization: `Bearer ${accessToken}` }, signal });
    if (!response.ok) throw await parsePublicError(response);
    const value = await response.json() as unknown;
    if (!value || typeof value !== 'object' || typeof (value as Record<string, unknown>).activated !== 'boolean') throw new Error('malformed_authentication_response');
    return { activated: (value as Record<string, unknown>).activated as boolean };
  }
  async prepareVerification(accessToken: string, contactKind: ContactKind, contact: string, signal?: AbortSignal): Promise<string> {
    const response = await boundedFetch(this.request, `${this.baseUrl}/api/auth/verification/prepare`, { method: 'POST', headers: { Accept: 'application/json', Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ contact_kind: contactKind, contact }), signal });
    if (!response.ok) throw await parsePublicError(response);
    const value = await response.json() as unknown; const id = value && typeof value === 'object' ? (value as Record<string, unknown>).challenge_id : undefined;
    if (typeof id !== 'string') throw new Error('malformed_authentication_response'); return id;
  }
  async completeVerification(accessToken: string, challengeId: string, code: string, signal?: AbortSignal): Promise<ActivationProgress> {
    const response = await boundedFetch(this.request, `${this.baseUrl}/api/auth/verification/complete`, { method: 'POST', headers: { Accept: 'application/json', Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ challenge_id: challengeId, code }), signal });
    if (!response.ok) throw await parsePublicError(response);
    const value = await response.json() as unknown;
    if (!value || typeof value !== 'object' || typeof (value as Record<string, unknown>).activated !== 'boolean') throw new Error('malformed_authentication_response');
    return { activated: (value as Record<string, unknown>).activated as boolean };
  }
  private exchange(path: string, credentials: Credentials, signal?: AbortSignal) {
    return this.session(path, { contact_kind: credentials.contactKind, contact: credentials.contact, password: credentials.password, device_id: this.device.deviceId, device_category: 'mobile', operating_system_family: this.device.operatingSystemFamily, application_version: this.device.applicationVersion }, signal);
  }
  private async session(path: string, body: Record<string, unknown>, signal?: AbortSignal) {
    const response = await boundedFetch(this.request, `${this.baseUrl}${path}`, { method: 'POST', headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal });
    if (!response.ok) throw await parsePublicError(response);
    try { return parseAuthenticationSession(await response.json()); } catch { throw new Error('malformed_authentication_response'); }
  }
}
