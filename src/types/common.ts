export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

/** Wire shape (snake_case) → app shape (camelCase). */
export interface PageWire<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export function mapPage<W, T>(wire: PageWire<W>, mapItem: (w: W) => T): Page<T> {
  return {
    items: wire.items.map(mapItem),
    total: wire.total,
    page: wire.page,
    pageSize: wire.page_size,
  };
}
