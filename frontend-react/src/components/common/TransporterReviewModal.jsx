import { useEffect, useId, useMemo, useRef, useState } from 'react'
import './TransporterReviewModal.css'

const MAX_COMMENT_LENGTH = 1000

function starsLabel(value) {
  return `${value} out of 5 stars`
}

export default function TransporterReviewModal({
  open,
  reviewTarget,
  title = 'Rate Your Transporter',
  submitLabel = 'Submit Review',
  submitting = false,
  error = '',
  dismissible = true,
  onClose,
  onSubmit,
}) {
  const dialogRef = useRef(null)
  const headingId = useId()
  const [rating, setRating] = useState(0)
  const [comment, setComment] = useState('')

  useEffect(() => {
    if (!open || !dialogRef.current) return
    dialogRef.current.focus()
  }, [open])

  const targetTitle = useMemo(() => {
    if (!reviewTarget) return ''
    const route = [reviewTarget.pickup_city, reviewTarget.dropoff_city].filter(Boolean).join(' -> ')
    const goods = reviewTarget.goods_type ? ` • ${reviewTarget.goods_type}` : ''
    return `${route}${goods}`
  }, [reviewTarget])

  if (!open || !reviewTarget) return null

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15, 23, 42, 0.55)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
        zIndex: 100,
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
        tabIndex={-1}
        onKeyDown={(event) => {
          if (event.key === 'Escape' && dismissible && !submitting) {
            onClose?.()
          }
        }}
        style={{
          width: 'min(100%, 560px)',
          borderRadius: 20,
          background: '#fff',
          boxShadow: '0 24px 60px rgba(15, 23, 42, 0.24)',
          padding: 24,
          outline: 'none',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <h2 id={headingId} style={{ margin: 0, fontSize: 24, fontWeight: 800, color: '#0f172a' }}>{title}</h2>
            <p style={{ margin: '8px 0 0', color: '#475569', fontSize: 14 }}>
              {reviewTarget.transporter_name || 'Transporter'}
            </p>
            {targetTitle && (
              <p style={{ margin: '6px 0 0', color: '#64748b', fontSize: 13 }}>{targetTitle}</p>
            )}
          </div>
          {dismissible && (
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              aria-label="Close review dialog"
              style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#64748b', fontSize: 20 }}
            >
              <i className="fas fa-times" aria-hidden="true"></i>
            </button>
          )}
        </div>

        <fieldset style={{ margin: '20px 0 0', padding: 0, border: 0, minWidth: 0 }}>
          <legend style={{ padding: 0, fontSize: 14, fontWeight: 700, color: '#0f172a' }}>
            Required star rating
          </legend>
          <div className="transporter-review-rating-group">
            {[1, 2, 3, 4, 5].map((value) => (
              <label
                key={value}
                className="transporter-review-rating-control"
                style={{
                  border: rating === value ? '2px solid #2563eb' : '1px solid #cbd5e1',
                  background: rating === value ? '#eff6ff' : '#fff',
                  color: rating >= value ? '#f59e0b' : '#94a3b8',
                  cursor: submitting ? 'default' : 'pointer',
                }}
              >
                <input
                  type="radio"
                  name="transporter-rating"
                  value={value}
                  checked={rating === value}
                  disabled={submitting}
                  onChange={() => setRating(value)}
                  className="transporter-review-rating-input"
                  aria-label={starsLabel(value)}
                />
                <span className="transporter-review-rating-visual">
                  <i className="fas fa-star" aria-hidden="true"></i>
                </span>
              </label>
            ))}
          </div>
          {!rating && (
            <div style={{ marginTop: 10, color: '#b91c1c', fontSize: 13 }}>
              Please select a rating from 1 to 5 stars.
            </div>
          )}
        </fieldset>

        <label style={{ display: 'grid', gap: 8, marginTop: 20 }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>Optional written review</span>
          <textarea
            value={comment}
            onChange={(event) => setComment(event.target.value.slice(0, MAX_COMMENT_LENGTH))}
            disabled={submitting}
            rows={5}
            placeholder="Share anything useful about communication, timing, or delivery quality."
            style={{
              resize: 'vertical',
              minHeight: 120,
              borderRadius: 14,
              border: '1px solid #cbd5e1',
              padding: 12,
              outline: 'none',
            }}
          />
          <span style={{ justifySelf: 'end', color: '#64748b', fontSize: 12 }}>
            {comment.length}/{MAX_COMMENT_LENGTH}
          </span>
        </label>

        {error && (
          <div style={{ marginTop: 16, borderRadius: 14, background: '#fef2f2', color: '#b91c1c', padding: 12, fontSize: 13 }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', marginTop: 22, flexWrap: 'wrap' }}>
          {dismissible && (
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              style={{
                minHeight: 42,
                borderRadius: 12,
                border: '1px solid #cbd5e1',
                background: '#fff',
                color: '#334155',
                fontWeight: 700,
                padding: '0 16px',
              }}
            >
              Later
            </button>
          )}
          <button
            type="button"
            disabled={submitting || !rating}
            onClick={() => onSubmit?.({ rating, comment })}
            style={{
              minHeight: 42,
              borderRadius: 12,
              border: 'none',
              background: submitting || !rating ? '#94a3b8' : '#2563eb',
              color: '#fff',
              fontWeight: 700,
              padding: '0 18px',
              cursor: submitting || !rating ? 'default' : 'pointer',
            }}
          >
            <i className={`fas ${submitting ? 'fa-spinner fa-spin' : 'fa-paper-plane'}`} aria-hidden="true" style={{ marginRight: 8 }}></i>
            {submitting ? 'Submitting...' : submitLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
