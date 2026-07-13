import { apiClient, unwrap } from "@/lib/apiClient";
import type { ApiResponse } from "@/types/api";
import type { AuthToken, User } from "@/types/models";

/** Authentication API calls. */
export const authService = {
  login: (email: string, password: string) =>
    unwrap<AuthToken>(apiClient.post<ApiResponse<AuthToken>>("/auth/login", { email, password })),

  register: (name: string, email: string, password: string) =>
    unwrap<AuthToken>(apiClient.post<ApiResponse<AuthToken>>("/auth/register", { name, email, password })),

  me: () => unwrap<User>(apiClient.get<ApiResponse<User>>("/auth/me")),
};
