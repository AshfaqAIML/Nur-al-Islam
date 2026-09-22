import { NextRequest } from "next/server";

/**
 * Shared admin gate (Phase 14 centralization).
 * Key: ADMIN_KEY env wins; the historic shared key remains as fallback so
 * existing deployments and the worker keep working until rotated.
 * Reads stay open by design (dashboard); all mutations require the key.
 */
export const DEFAULT_ADMIN_KEY = "nur-al-usul-admin";

export function adminKey(): string {
  const env = (process.env.ADMIN_KEY ?? "").trim();
  return env.length > 0 ? env : DEFAULT_ADMIN_KEY;
}

export function checkAdmin(req: NextRequest): boolean {
  return req.headers.get("x-admin-key") === adminKey();
}
