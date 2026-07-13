import { Navigate, Outlet } from "react-router-dom";

import { Spinner } from "@/components/ui/misc";
import { useAuth } from "@/contexts/AuthContext";

/** Guards routes that require authentication. */
export function ProtectedRoute() {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex min-h-screen items-center justify-center"><Spinner label="Loading…" /></div>;
  if (!user) return <Navigate to="/login" replace />;
  return <Outlet />;
}
