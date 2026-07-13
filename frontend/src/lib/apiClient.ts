import axios, { AxiosError } from "axios";

import type { ApiResponse } from "@/types/api";

const TOKEN_KEY = "datapilot_token";

/** Central axios instance. Every request in the app goes through this client. */
export const apiClient = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
});

/** Attach the bearer token to every outgoing request. */
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

/** Normalize backend errors into a readable message and handle 401s. */
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiResponse<unknown>>) => {
    if (error.response?.status === 401 && !location.pathname.startsWith("/login")) {
      localStorage.removeItem(TOKEN_KEY);
      location.href = "/login";
    }
    const message =
      error.response?.data?.message ||
      error.response?.data?.errors?.[0]?.message ||
      error.message ||
      "Something went wrong.";
    return Promise.reject(new Error(message));
  }
);

/** Unwrap the standard `{success, data, ...}` envelope, returning `data`. */
export async function unwrap<T>(promise: Promise<{ data: ApiResponse<T> }>): Promise<T> {
  const { data } = await promise;
  if (!data.success) throw new Error(data.message);
  return data.data as T;
}

export const tokenStorage = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

/** Base URL for non-JSON endpoints (file downloads, SSE). */
export const API_BASE = "/api/v1";
