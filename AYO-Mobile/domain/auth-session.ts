export type IdentityKind = 'anonymous' | 'rider' | 'driver' | 'staff' | 'administrator' | 'service' | 'merchant' | 'service_provider';

export type AuthenticatedSession = Readonly<{
  identityId: string;
  sessionId: string;
  identityKind: IdentityKind;
  accessToken: string;
  accessExpiresAt: string;
  refreshToken: string;
  refreshExpiresAt: string;
}>;

export type SessionIdentity = Readonly<{
  identityId: string;
  identityKind: IdentityKind;
}>;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function timestamp(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value)) && /(?:Z|[+-]\d{2}:\d{2})$/.test(value);
}

function token(value: unknown): value is string {
  return typeof value === 'string' && value.length >= 32 && value.length <= 4096;
}

export function parseAuthenticationSession(value: unknown): AuthenticatedSession {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('malformed_authentication_response');
  const input = value as Record<string, unknown>;
  const identityKind = input.identity_type;
  if (
    typeof input.identity_id !== 'string' || !UUID.test(input.identity_id) ||
    typeof input.session_id !== 'string' || !UUID.test(input.session_id) ||
    !['anonymous', 'rider', 'driver', 'staff', 'administrator', 'service', 'merchant', 'service_provider'].includes(String(identityKind)) ||
    !token(input.access_token) || !timestamp(input.access_expires_at) ||
    !token(input.refresh_token) || !timestamp(input.refresh_expires_at) ||
    input.token_type !== 'Bearer' ||
    Date.parse(input.access_expires_at) >= Date.parse(input.refresh_expires_at)
  ) throw new Error('malformed_authentication_response');
  return {
    identityId: input.identity_id,
    sessionId: input.session_id,
    identityKind: identityKind as IdentityKind,
    accessToken: input.access_token,
    accessExpiresAt: input.access_expires_at,
    refreshToken: input.refresh_token,
    refreshExpiresAt: input.refresh_expires_at,
  };
}

export function parseStoredSession(value: unknown): AuthenticatedSession {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('malformed_stored_session');
  const stored = value as Record<string, unknown>;
  return parseAuthenticationSession({
    identity_id: stored.identityId,
    session_id: stored.sessionId,
    identity_type: stored.identityKind,
    access_token: stored.accessToken,
    access_expires_at: stored.accessExpiresAt,
    refresh_token: stored.refreshToken,
    refresh_expires_at: stored.refreshExpiresAt,
    token_type: 'Bearer',
  });
}
