import { CourierHandoffConflictError, CourierHandoffNoLongerCurrentError, parseCourierCustodyRead, parseCourierPickup, projectCourierHandoff, type CourierHandoffSnapshot } from '../domain/courier-handoff-status.ts';
import { PublicApiError } from './api-foundation.ts';
type AuthenticatedRead = (path: string, signal?: AbortSignal) => Promise<unknown>;

export class CourierHandoffStatusService {
  private readonly read: AuthenticatedRead;
  constructor(read: AuthenticatedRead) { this.read = read; }
  async load(pickupId: string, signal?: AbortSignal): Promise<CourierHandoffSnapshot> {
    let pickup: ReturnType<typeof parseCourierPickup>;
    try { pickup = parseCourierPickup(await this.read(`/mobile/courier-pickups/${encodeURIComponent(pickupId)}`, signal)); }
    catch (error) {
      if (error instanceof PublicApiError && (error.status === 403 || error.status === 404)) throw new CourierHandoffNoLongerCurrentError();
      throw error;
    }
    if (pickup.pickupId !== pickupId.toLowerCase()) throw new CourierHandoffConflictError();
    if (signal?.aborted) throw new PublicApiError('request_cancelled');
    let custody;
    try { custody = parseCourierCustodyRead(await this.read(`/mobile/courier-pickups/${encodeURIComponent(pickupId)}/custody`, signal)); }
    catch (error) {
      if (error instanceof PublicApiError && (error.status === 403 || error.status === 404)) throw new CourierHandoffNoLongerCurrentError();
      throw error;
    }
    return projectCourierHandoff(pickup, custody);
  }
}
