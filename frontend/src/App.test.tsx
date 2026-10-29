import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, test } from "vitest"
import { App } from "./App"

test("test_page_shows_title", () => {
  render(<App />)
  expect(screen.getByRole("heading", { name: "Moderation" })).toBeInTheDocument()
})

test("test_switching_workspace_picks_that_admin", async () => {
  const user = userEvent.setup()
  render(<App />)
  await user.selectOptions(screen.getByLabelText("Workspace"), "ws_unverified")
  expect(screen.getByLabelText("User")).toHaveValue("admin_u")
  expect(screen.getByText("Signed in as admin_u in ws_unverified")).toBeInTheDocument()
})
