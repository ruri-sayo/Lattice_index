function defaultApiBase() {
  return '';
}

export const API_BASE = (import.meta.env.VITE_API_BASE ?? defaultApiBase()).replace(/\/$/, '');

export type Location = {
  id: number;
  name: string;
  sort_order: number;
  is_active: number;
};

export type CopyRow = {
  copy_id: number;
  book_id: number;
  title: string;
  author?: string;
  isbn13?: string;
  series_name?: string;
  volume_number?: string;
  publisher?: string;
  label?: string;
  category?: string;
  description?: string;
  cover_url?: string;
  location_id?: number;
  location_name?: string;
  location_detail?: string;
  ownership_status: 'owned' | 'disposed' | 'lost' | 'sold';
  condition?: string;
  memo?: string;
  related_copies?: CopyRow[];
};

export type LookupResult = {
  isbn13: string;
  source: string;
  title?: string;
  author?: string;
  publisher?: string;
  published_date?: string;
  page_count?: number;
  category?: string;
  description?: string;
  cover_url?: string;
  raw?: unknown;
};

export type CsvImportResult = {
  imported: number;
  skipped: number;
  errors: Array<{ line: number; detail: string }>;
  accepted_columns: string[];
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail ?? 'API request failed');
  }
  return response.json() as Promise<T>;
}

export const api = {
  locations: () => request<Location[]>('/api/locations?include_inactive=true'),
  createLocation: (name: string) => request<Location>('/api/locations', { method: 'POST', body: JSON.stringify({ name }) }),
  updateLocation: (id: number, body: Partial<Location>) =>
    request<Location>(`/api/locations/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  copies: () => request<CopyRow[]>('/api/copies?limit=80'),
  copy: (id: number) => request<CopyRow>(`/api/copies/${id}`),
  search: (q: string, location = '') => {
    const params = new URLSearchParams();
    if (q.trim()) params.set('q', q.trim());
    if (location) params.set('location', location);
    return request<CopyRow[]>(`/api/search?${params.toString()}`);
  },
  lookup: (isbn: string) => request<LookupResult>('/api/books/lookup', { method: 'POST', body: JSON.stringify({ isbn }) }),
  createBook: (body: unknown) => request<{ status: string; book_id?: number; copy_id?: number; existing_book_id?: number; existing_copies?: CopyRow[]; message?: string }>('/api/books', {
    method: 'POST',
    body: JSON.stringify(body)
  }),
  updateCopy: (id: number, body: unknown) => request<CopyRow>(`/api/copies/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  importCsv: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await fetch(`${API_BASE}/api/import/csv`, {
      method: 'POST',
      body: formData
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail ?? 'CSV import failed');
    }
    return response.json() as Promise<CsvImportResult>;
  }
};
