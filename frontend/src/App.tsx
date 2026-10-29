import { useState } from "react"
import { createClient } from "./api/client"
import type { Caller } from "./api/types"
import { SubmitForm } from "./components/SubmitForm"
import { ReviewQueue } from "./components/ReviewQueue"
import { WhoSelect } from "./components/WhoSelect"

export function App() {
  const [client] = useState(() => createClient())
  const [caller, setCaller] = useState<Caller>({ workspaceId: "ws_verified", userId: "admin_v" })
  const [reviewRefresh, setReviewRefresh] = useState(0)
  return (
    <main>
      <h1>Moderation</h1>
      <WhoSelect caller={caller} onChange={setCaller} />
      <p>
        Signed in as {caller.userId} in {caller.workspaceId}
      </p>
      <SubmitForm client={client} caller={caller} onSettled={() => setReviewRefresh((value) => value + 1)} />
      <ReviewQueue client={client} caller={caller} refreshKey={reviewRefresh} />
    </main>
  )
}
