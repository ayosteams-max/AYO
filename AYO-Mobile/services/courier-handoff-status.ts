import { CourierHandoffConflictError, parseCourierCustody, parseCourierPickup, projectCourierHandoff, type CourierHandoffSnapshot } from '../domain/courier-handoff-status.ts';
import { PublicApiError } from './api-foundation.ts';
type AuthenticatedRead = (path: string, signal?: AbortSignal) => Promise<unknown>;

export class CourierHandoffStatusService {
  private readonly read: AuthenticatedRead;
  constructor(read: AuthenticatedRead) { this.read = read; }
  async load(pickupId: string, signal?: AbortSignal): Promise<CourierHandoffSnapshot> {
    const pickup = parseCourierPickup(await this.read(`/mobile/courier-pickups/${encodeURIComponent(pickupId)}`, signal));
    if (pickup.pickupId !== pickupId.toLowerCase()) throw new CourierHandoffConflictError();
    if (signal?.aborted) throw new PublicApiError('request_cancelled');
    let custody;
    try { custody = parseCourierCustody(await this.read(`/mobile/courier-pickups/${encodeURIComponent(pickupId)}/custody`, signal)); }
    catch (error) { if (!(error instanceof PublicApiError) || error.status !== 404) throw error; }
    return projectCourierHandoff(pickup, custody);
  }
}
