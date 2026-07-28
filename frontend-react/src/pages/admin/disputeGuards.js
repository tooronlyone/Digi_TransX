// Pure, testable guards for admin one-time-dispute evidence race-safety (FIX B).
// Kept as standalone pure functions so they can be verified deterministically
// without a browser/React test runner.

export function normalizeDisputeId(value) {
  if (typeof value === 'number') {
    return Number.isSafeInteger(value) && value > 0 ? String(value) : null
  }
  if (typeof value !== 'string') return null
  const normalized = value.trim()
  return /^[1-9]\d*$/.test(normalized) ? normalized : null
}

export function disputeDetailFromResponse(payload) {
  return payload && typeof payload === 'object' && payload.dispute && typeof payload.dispute === 'object'
    ? payload.dispute
    : null
}

// True only when the loaded evidence belongs to the dispute the admin currently
// has selected. Resolution is gated on this.
export function detailMatchesSelection(detail, selected) {
  const detailId = normalizeDisputeId(detail?.id)
  const selectedId = normalizeDisputeId(selected?.id)
  return detailId !== null && detailId === selectedId
}

// True only when a detail response should be applied: it is the LATEST request
// (its token still matches) AND its dispute id equals the currently selected
// dispute id. A stale or mismatched response is dropped.
export function shouldAcceptDetail(responseDisputeId, selectedId, reqToken, latestToken) {
  const responseId = normalizeDisputeId(responseDisputeId)
  const currentId = normalizeDisputeId(selectedId)
  return (
    reqToken === latestToken &&
    responseId !== null &&
    responseId === currentId
  )
}

export function detailRequestError(error, mounted, reqToken, latestToken) {
  if (error?.name === 'AbortError' || !mounted || reqToken !== latestToken) return null
  return error?.message || 'Unable to load dispute details.'
}
