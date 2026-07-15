import { useEffect, useState } from 'react';

import type { Destination, DestinationCategory, DestinationSearchGateway } from '@/domain/destination';

type SearchState =
  | { status: 'loading'; results: readonly Destination[] }
  | { status: 'ready'; results: readonly Destination[] }
  | { status: 'error'; results: readonly Destination[] };

export function useDestinationSearch(
  gateway: DestinationSearchGateway,
  query: string,
  category?: DestinationCategory,
): SearchState {
  const [state, setState] = useState<SearchState>({ status: 'loading', results: [] });

  useEffect(() => {
    const controller = new AbortController();
    setState((current) => ({ status: 'loading', results: current.results }));

    const timer = setTimeout(() => {
      gateway.search({ query, category, limit: 20, signal: controller.signal })
        .then((results) => setState({ status: 'ready', results }))
        .catch((error: unknown) => {
          if (error instanceof Error && error.name === 'AbortError') return;
          setState({ status: 'error', results: [] });
        });
    }, 180);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [category, gateway, query]);

  return state;
}
