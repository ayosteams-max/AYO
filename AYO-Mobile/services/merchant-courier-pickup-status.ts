import {
  parseMerchantCourierPickupIdentifier,
  parseMerchantCourierPickupStatus,
  type MerchantCourierPickupSnapshot,
} from '../domain/merchant-courier-pickup-status.ts';

export type AuthenticatedMerchantCourierPickupRead = (path: string, signal?: AbortSignal) => Promise<unknown>;

export class MerchantCourierPickupStatusService {
  private readonly read: AuthenticatedMerchantCourierPickupRead;

  constructor(read: AuthenticatedMerchantCourierPickupRead) { this.read = read; }

  async load(merchantId: string, orderId: string, signal?: AbortSignal): Promise<MerchantCourierPickupSnapshot> {
    const merchant = parseMerchantCourierPickupIdentifier(merchantId);
    const order = parseMerchantCourierPickupIdentifier(orderId);
    const value = await this.read(
      `/mobile/merchants/${encodeURIComponent(merchant)}/orders/${encodeURIComponent(order)}/courier-pickup`,
      signal,
    );
    return parseMerchantCourierPickupStatus(value);
  }
}
