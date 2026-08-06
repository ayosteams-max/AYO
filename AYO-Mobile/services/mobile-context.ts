import { parseMobileContext, type MobileContextSnapshot } from '../domain/mobile-context.ts';

export type AuthenticatedGet = (path: string, signal?: AbortSignal) => Promise<unknown>;

export class MobileContextService {
  private readonly get: AuthenticatedGet;
  constructor(get: AuthenticatedGet) { this.get = get; }
  async load(signal?: AbortSignal): Promise<MobileContextSnapshot> {
    return parseMobileContext(await this.get('/api/mobile/context', signal));
  }
}
