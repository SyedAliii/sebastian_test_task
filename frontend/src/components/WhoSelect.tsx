import type { Caller } from "../api/types"

const USERS: Record<Caller["workspaceId"], Caller["userId"][]> = {
  ws_verified: ["admin_v", "member_v"],
  ws_unverified: ["admin_u", "member_u"],
}

type WhoSelectProps = {
  caller: Caller
  onChange: (caller: Caller) => void
}

export function WhoSelect({ caller, onChange }: WhoSelectProps) {
  return (
    <div>
      <label htmlFor="workspace">Workspace</label>
      <select
        id="workspace"
        value={caller.workspaceId}
        onChange={(event) => {
          const workspaceId = event.target.value as Caller["workspaceId"]
          const userId = workspaceId === "ws_verified" ? "admin_v" : "admin_u"
          onChange({ workspaceId, userId })
        }}
      >
        <option value="ws_verified">ws_verified</option>
        <option value="ws_unverified">ws_unverified</option>
      </select>
      <label htmlFor="user">User</label>
      <select
        id="user"
        value={caller.userId}
        onChange={(event) => {
          onChange({ ...caller, userId: event.target.value as Caller["userId"] })
        }}
      >
        {USERS[caller.workspaceId].map((userId) => (
          <option key={userId} value={userId}>
            {userId}
          </option>
        ))}
      </select>
    </div>
  )
}
