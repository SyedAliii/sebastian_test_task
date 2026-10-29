export type How = "upload" | "generation"

export function buildMediaBody(parsedJson: Record<string, unknown>, how: How, prompt: string): Record<string, unknown> {
  const body = { ...parsedJson }
  if (how === "generation") {
    body.source = "generation"
    body.prompt = prompt
    return body
  }
  body.source = "upload"
  delete body.prompt
  return body
}
