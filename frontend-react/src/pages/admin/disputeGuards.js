// Pure, testable guards for admin one-time-dispute evidence race-safety (FIX B).
// Kept as standalone pure functions so they can be verified deterministically
// without a browser/React test runner.

// True only when the loaded evidence belongs to the dispute the admin currently
// has selected. Resolution is gated on this.
export function detailMatchesSelection(detail, selected) {
  return !!(detail && selected && detail.id != null && detail.id === selected.id)
}

// True only when a detail response should be applied: it is the LATEST request
// (its token still matches) AND its dispute id equals the currently selected
// dispute id. A stale or mismatched response is dropped.
export function shouldAcceptDetail(responseDisputeId, selectedId, reqToken, latestToken) {
  return (
    reqToken === latestToken &&
    responseDisputeId != null &&
    selectedId != null &&
    responseDisputeId === selectedId
  )
}
