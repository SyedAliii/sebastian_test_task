export function logStep(step: string, fields: Record<string, string | number>): void {
  const parts = Object.entries(fields).map(([key, value]) => `${key}=${value}`)
  console.info([`step=${step}`, ...parts].join(" "))
}
