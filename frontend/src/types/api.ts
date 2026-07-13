/** Shared API envelope and pagination types mirroring the backend schemas. */

export interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T | null;
  errors: { code: string; message: string; field?: string }[];
  timestamp: string;
}

export interface PageMeta {
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface Paginated<T> {
  items: T[];
  meta: PageMeta;
}
