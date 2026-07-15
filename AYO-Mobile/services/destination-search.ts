import type {
  Destination,
  DestinationSearchGateway,
  DestinationSearchRequest,
} from '../domain/destination.ts';

const OFFLINE_DESTINATIONS: readonly Destination[] = [
  { id: 'saved-home', name: 'Home', address: 'Bole, Addis Ababa', category: 'saved' },
  { id: 'saved-work', name: 'Work', address: 'Kazanchis, Addis Ababa', category: 'saved' },
  { id: 'recent-meskel', name: 'Meskel Square', address: 'Kirkos, Addis Ababa', category: 'recent' },
  { id: 'recent-unity', name: 'Unity Park', address: 'Arat Kilo, Addis Ababa', category: 'recent' },
  { id: 'airport-add', name: 'Addis Ababa Bole International Airport', address: 'Bole, Addis Ababa', category: 'airport' },
  { id: 'place-edna', name: 'Edna Mall', address: 'Cameroon Street, Bole', category: 'destination' },
  { id: 'place-century', name: 'Century Mall', address: 'Gurd Shola, Addis Ababa', category: 'destination' },
  { id: 'place-sarbet', name: 'Sarbet', address: 'Nifas Silk-Lafto, Addis Ababa', category: 'destination' },
];

function normalize(value: string) {
  return value.trim().toLocaleLowerCase();
}

/**
 * Bounded offline adapter for the prototype. Production providers implement the
 * same gateway and may merge server search with encrypted on-device user places.
 */
export class OfflineDestinationSearchGateway implements DestinationSearchGateway {
  private readonly destinations: readonly Destination[];

  constructor(destinations: readonly Destination[] = OFFLINE_DESTINATIONS) {
    this.destinations = destinations;
  }

  async search(request: DestinationSearchRequest): Promise<readonly Destination[]> {
    if (request.signal?.aborted) throw new DOMException('Search cancelled', 'AbortError');

    const query = normalize(request.query);
    return this.destinations
      .filter((item) => !request.category || item.category === request.category)
      .filter((item) => !query || normalize(`${item.name} ${item.address}`).includes(query))
      .slice(0, Math.max(0, request.limit));
  }
}

export const destinationSearchGateway: DestinationSearchGateway =
  new OfflineDestinationSearchGateway();
