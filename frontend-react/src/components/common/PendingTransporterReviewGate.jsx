import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiGet, apiSend } from '../../pages/client/clientUtils'
import TransporterReviewModal from './TransporterReviewModal'
import { REVIEW_REQUIRED_EVENT } from './reviewEvents'

export default function PendingTransporterReviewGate({ basePath }) {
  const [pendingReviews, setPendingReviews] = useState([])
  const [activeReview, setActiveReview] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function loadPending() {
    try {
      const json = await apiGet('/api/reviews/pending')
      const rows = json.pending_reviews || []
      setPendingReviews(rows)
      setActiveReview((current) => {
        if (!current) return null
        return rows.find(
          (item) => item.shipment_id === current.shipment_id && item.trip_id === current.trip_id,
        ) || null
      })
    } catch {
      /* best effort */
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadPending()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [])

  useEffect(() => {
    function handleReviewRequired(event) {
      const detail = event.detail
      if (!detail) return
      setPendingReviews((current) => {
        const exists = current.some((item) => item.shipment_id === detail.shipment_id && item.trip_id === detail.trip_id)
        return exists ? current : [detail, ...current]
      })
      setActiveReview(detail)
      setError('')
    }

    window.addEventListener(REVIEW_REQUIRED_EVENT, handleReviewRequired)
    return () => window.removeEventListener(REVIEW_REQUIRED_EVENT, handleReviewRequired)
  }, [])

  async function submitReview({ rating, comment }) {
    if (!activeReview) return
    setSubmitting(true)
    setError('')
    try {
      await apiSend(`/api/orders/${activeReview.shipment_id}/trips/${activeReview.trip_id}/review`, { rating, comment })
      const remaining = pendingReviews.filter(
        (item) => !(item.shipment_id === activeReview.shipment_id && item.trip_id === activeReview.trip_id),
      )
      setPendingReviews(remaining)
      setActiveReview(remaining[0] || null)
    } catch (submitError) {
      setError(submitError.message || 'Unable to submit review right now.')
    } finally {
      setSubmitting(false)
      loadPending()
    }
  }

  const bannerText = useMemo(() => {
    if (!pendingReviews.length) return ''
    if (pendingReviews.length === 1) return 'A completed delivery is waiting for your mandatory transporter review.'
    return `${pendingReviews.length} completed deliveries are waiting for your mandatory transporter reviews.`
  }, [pendingReviews.length])

  if (!pendingReviews.length && !activeReview) return null

  return (
    <>
      {pendingReviews.length > 0 && (
        <div
          style={{
            marginBottom: 18,
            borderRadius: 18,
            border: '1px solid #fde68a',
            background: '#fffbeb',
            padding: 16,
            display: 'flex',
            justifyContent: 'space-between',
            gap: 12,
            alignItems: 'center',
            flexWrap: 'wrap',
          }}
        >
          <div>
            <div style={{ fontWeight: 800, color: '#92400e' }}>Mandatory review required</div>
            <div style={{ marginTop: 4, color: '#78350f', fontSize: 14 }}>{bannerText}</div>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {pendingReviews.length > 0 && (
              <button
                type="button"
                onClick={() => {
                  setActiveReview(pendingReviews[0])
                  setError('')
                }}
                style={{
                  minHeight: 40,
                  borderRadius: 12,
                  border: 'none',
                  background: '#d97706',
                  color: '#fff',
                  fontWeight: 700,
                  padding: '0 16px',
                }}
              >
                Review now
              </button>
            )}
            {pendingReviews.length > 0 && (
              <Link
                to={`${basePath}/order/${pendingReviews[0].shipment_id}`}
                style={{
                  minHeight: 40,
                  borderRadius: 12,
                  border: '1px solid #f59e0b',
                  background: '#fff',
                  color: '#92400e',
                  fontWeight: 700,
                  padding: '9px 16px',
                  textDecoration: 'none',
                }}
              >
                Open order
              </Link>
            )}
          </div>
        </div>
      )}

      <TransporterReviewModal
        key={activeReview ? `${activeReview.shipment_id}-${activeReview.trip_id}` : 'pending-review'}
        open={!!activeReview}
        reviewTarget={activeReview}
        title="Mandatory Transporter Review"
        submitLabel="Submit Mandatory Review"
        submitting={submitting}
        error={error}
        dismissible
        onClose={() => {
          if (submitting) return
          setActiveReview(null)
          setError('')
        }}
        onSubmit={submitReview}
      />
    </>
  )
}
