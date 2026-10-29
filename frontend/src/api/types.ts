export type Caller = {
  workspaceId: "ws_verified" | "ws_unverified"
  userId: "admin_v" | "member_v" | "admin_u" | "member_u"
}

export type Media = {
  id: string
  status: "pending" | "published" | "held" | "blocked"
  reasons: string[]
}

export type ApiSuccess<T> = { ok: true; status: number; data: T }
export type ApiFailure = { ok: false; status: number; message: string; reasons?: string[] }
export type ApiResult<T> = ApiSuccess<T> | ApiFailure
