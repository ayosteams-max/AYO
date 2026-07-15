export type DestinationCategory = 'destination' | 'saved' | 'recent' | 'airport';

export type Destination = Readonly<{
  id: string;
  name: string;
  address: string;
  category: DestinationCategory;
  latitude?: number;
  longitude?: number;
}>;

export type DestinationSearchRequest = Readonly<{
  query: string;
  category?: DestinationCategory;
  limit: number;
  signal?: AbortSignal;
}>;

export interface DestinationSearchGateway {
  search(request: DestinationSearchRequest): Promise<readonly Destination[]>;
}
