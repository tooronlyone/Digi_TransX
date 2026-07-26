export const REVIEW_REQUIRED_EVENT = 'digitransx:review-required'

export function openPendingReviewModal(pendingReview) {
  window.dispatchEvent(new CustomEvent(REVIEW_REQUIRED_EVENT, { detail: pendingReview }))
}
