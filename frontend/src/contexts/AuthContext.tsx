import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { tokenStorage } from "@/lib/apiClient";
import { authService } from "@/services/authService";
import type { User } from "@/types/models";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

/** Provides authentication state to the app (the only global context). */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = tokenStorage.get();
    if (!token) {
      setLoading(false);
      return;
    }
    authService
      .me()
      .then(setUser)
      .catch(() => tokenStorage.clear())
      .finally(() => setLoading(false));
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      login: async (email, password) => {
        const token = await authService.login(email, password);
        tokenStorage.set(token.access_token);
        setUser(token.user);
      },
      register: async (name, email, password) => {
        const token = await authService.register(name, email, password);
        tokenStorage.set(token.access_token);
        setUser(token.user);
      },
      logout: () => {
        tokenStorage.clear();
        setUser(null);
      },
    }),
    [user, loading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Access the authentication state. */
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
