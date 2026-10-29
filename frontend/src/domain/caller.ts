import type { Caller } from "../api/types"

export function isAdmin(userId: Caller["userId"]): boolean {
  return userId.startsWith("admin_")
}
