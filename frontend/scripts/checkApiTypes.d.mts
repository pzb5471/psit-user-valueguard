export type CheckResult = { ok: true } | { ok: false; message: string }
export function compareSources(regenerated: string, committed: string): CheckResult
export function checkCommittedTypes(): Promise<CheckResult>
