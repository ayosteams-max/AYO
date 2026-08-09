import { parseMerchantOperationalOrders, type MerchantOperationalOrder } from '../domain/merchant-operational-order.ts';

export type AuthenticatedMerchantOrderRead = (path: string, signal?: AbortSignal) => Promise<unknown>;

export class MerchantOperationalOrderService {
  private readonly read: AuthenticatedMerchantOrderRead;
  constructor(read: AuthenticatedMerchantOrderRead) { this.read = read; }

  async list(merchantId: string, signal?: AbortSignal): Promise<readonly MerchantOperationalOrder[]> {
    return parseMerchantOperationalOrders(
      await this.read(`/mobile/merchants/${encodeURIComponent(merchantId)}/orders?limit=25`, signal),
      merchantId,
    );
  }
}
