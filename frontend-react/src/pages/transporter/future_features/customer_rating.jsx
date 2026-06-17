// STATUS: disabled — not connected to any route or button.
// Moved here for future re-integration.
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import TransporterLayout from '../../components/transporter/TransporterLayout'
import { useApi } from '../../hooks/useApi'

const EMPTY_DISTRIBUTION = [5, 4, 3, 2, 1].map(stars => ({
  stars,
  count: 0,
  percentage: 0,
}))

const EMPTY_OVERVIEW = {
  overall: 0,
  total_reviews: 0,
  written_reviews: 0,
  positive_reviews: 0,
  distribution: EMPTY_DISTRIBUTION,
  recent_reviews: [],
  trends: [],
}

const EMPTY_LEADERBOARD = {
  podium: [],
  nearby: [],
  current_user: null,
}

function formatDate(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Recent'
  return date.toLocaleDateString('en-PK', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function formatMoney(value) {
  return `PKR ${(parseFloat(value) || 0).toLocaleString('en-PK', {
    maximumFractionDigits: 0,
  })}`
}

function initials(name) {
  const text = String(name || '').trim()
  if (!text) return 'C'
  const parts = text.split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
  return text.slice(0, 2).toUpperCase()
}

function renderStars(rating) {
  const full = Math.max(0, Math.min(5, Math.round(parseFloat(rating) || 0)))
  return Array.from({ length: 5 }, (_, index) => (
    <i
      key={`${rating}-${index}`}
      className={`${index < full ? 'fas' : 'far'} fa-star`}
      aria-hidden="true"
    ></i>
  ))
}

export default function CustomerRating() {
  const { get } = useApi()
  const [overview, setOverview] = useState(EMPTY_OVERVIEW)
  const [leaderboard, setLeaderboard] = useState(EMPTY_LEADERBOARD)
  const [profileStats, setProfileStats] = useState({
    total_jobs: 0,
    total_earnings: 0,
    avg_rating: 0,
  })
  const [loading, setLoading] = useState(true)
  const [reviewFilter, setReviewFilter] = useState('all')
  const [lastUpdated, setLastUpdated] = useState('')

  function load() {
    setLoading(true)
    Promise.allSettled([
      get('/api/profile'),
      get('/api/ratings/overview'),
      get('/api/leaderboard?limit=5&page=1'),
    ])
      .then(([profileRes, overviewRes, leaderboardRes]) => {
        if (profileRes.status === 'fulfilled' && profileRes.value?.success) {
          setProfileStats({
            total_jobs: profileRes.value?.data?.stats?.total_jobs || 0,
            total_earnings: profileRes.value?.data?.stats?.total_earnings || 0,
            avg_rating: profileRes.value?.data?.stats?.avg_rating || 0,
          })
        }

        if (overviewRes.status === 'fulfilled' && overviewRes.value?.success) {
          setOverview({
            ...EMPTY_OVERVIEW,
            ...(overviewRes.value.overview || {}),
            distribution: overviewRes.value?.overview?.distribution?.length
              ? overviewRes.value.overview.distribution
              : EMPTY_DISTRIBUTION,
          })
        } else {
          setOverview(EMPTY_OVERVIEW)
        }

        if (leaderboardRes.status === 'fulfilled' && leaderboardRes.value?.success) {
          setLeaderboard({
            podium: leaderboardRes.value.podium || [],
            nearby: leaderboardRes.value.nearby || [],
            current_user: leaderboardRes.value.current_user || null,
          })
        } else {
          setLeaderboard(EMPTY_LEADERBOARD)
        }

        setLastUpdated(new Date().toLocaleTimeString('en-PK', {
          hour: 'numeric',
          minute: '2-digit',
        }))
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [])

  const filteredReviews = useMemo(() => {
    const rows = overview.recent_reviews || []
    if (reviewFilter === 'all') return rows
    if (reviewFilter === 'written') return rows.filter(review => String(review.review || '').trim())
    return rows.filter(review => String(review.rating) === String(reviewFilter))
  }, [overview.recent_reviews, reviewFilter])

  const positiveShare = useMemo(() => {
    if (!overview.total_reviews) return 0
    return Math.round(((overview.positive_reviews || 0) * 100) / overview.total_reviews)
  }, [overview.positive_reviews, overview.total_reviews])

  const ratingValue = parseFloat(overview.overall || profileStats.avg_rating || 0)
  const currentRank = leaderboard.current_user?.rank || '--'
  const completionRate = leaderboard.current_user?.completion_rate || 0
  const reviewCount = overview.total_reviews || leaderboard.current_user?.review_count || 0

  const trendSummary = useMemo(() => {
    const points = (overview.trends || []).filter(point => parseFloat(point.rating || 0) > 0)
    if (points.length < 2) return 'Ratings trend will appear once more review history is available.'
    const first = parseFloat(points[0].rating || 0)
    const last = parseFloat(points[points.length - 1].rating || 0)
    if (last > first) return 'Customer satisfaction is moving upward over recent months.'
    if (last < first) return 'Recent months need attention to recover rating momentum.'
    return 'Ratings have stayed stable across recent months.'
  }, [overview.trends])

  const reputationNote = useMemo(() => {
    if (!reviewCount) return 'No client ratings have been recorded yet. Complete jobs and collect delivery feedback to build your reputation.'
    if (ratingValue >= 4.5) return 'Your reputation is strong. Keep response times low and service quality consistent to protect your lead.'
    if (ratingValue >= 4) return 'Your ratings are healthy. A few more 5-star reviews can push you into a stronger competitive position.'
    return 'There is room to improve. Focus on reliability, communication, and delivery discipline to lift future reviews.'
  }, [ratingValue, reviewCount])

  const statCards = [
    {
      key: 'average',
      icon: 'fa-star',
      iconClass: 'rating-icon',
      label: 'Average Rating',
      value: `${ratingValue.toFixed(1)} / 5`,
      meta: reviewCount ? `${reviewCount} customer reviews` : 'No reviews yet',
    },
    {
      key: 'reviews',
      icon: 'fa-comments',
      iconClass: 'reviews-icon',
      label: 'Reviews Received',
      value: `${reviewCount}`,
      meta: `${overview.written_reviews || 0} with written feedback`,
    },
    {
      key: 'rank',
      icon: 'fa-trophy',
      iconClass: 'rank-icon',
      label: 'Platform Rank',
      value: currentRank === '--' ? '--' : `#${currentRank}`,
      meta: leaderboard.current_user ? `${completionRate}% completion rate` : 'Rank updates after reviews sync',
    },
    {
      key: 'positive',
      icon: 'fa-thumbs-up',
      iconClass: 'response-icon',
      label: 'Positive Review Share',
      value: `${positiveShare}%`,
      meta: 'Based on 4-star and 5-star reviews',
    },
  ]

  return (
    <TransporterLayout>
      <div className="page-rating">
        <div className="top-bar">
          <div className="page-title">
            <h1>Customer Ratings</h1>
            <p>Track review quality, customer feedback, and your reputation across the Digi_TransX platform.</p>
          </div>

          <button type="button" className="refresh-btn" onClick={load} disabled={loading}>
            <i className={`fas ${loading ? 'fa-spinner fa-spin' : 'fa-rotate-right'}`}></i>
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>

        <div className="page-shortcuts">
          <Link to="/transporter/dashboard" className="page-shortcut">
            <i className="fas fa-tachometer-alt"></i><span>Dashboard</span>
          </Link>
          <Link to="/transporter/jobs/history" className="page-shortcut">
            <i className="fas fa-history"></i><span>Job History</span>
          </Link>
          <Link to="/transporter/earnings" className="page-shortcut">
            <i className="fas fa-wallet"></i><span>Earnings</span>
          </Link>
          <Link to="/transporter/profile" className="page-shortcut">
            <i className="fas fa-user-circle"></i><span>Profile</span>
          </Link>
          <Link to="/transporter/rating" className="page-shortcut active">
            <i className="fas fa-star"></i><span>Ratings</span>
          </Link>
        </div>

        {loading ? (
          <div className="loading-state">
            <i className="fas fa-spinner fa-spin"></i>
            <p>Loading your rating dashboard...</p>
          </div>
        ) : (
          <>
            <div className="rating-summary-grid">
              {statCards.map(card => (
                <div className="rating-summary-card" key={card.key}>
                  <div className="summary-card-head">
                    <div>
                      <div className="summary-value">{card.value}</div>
                      <div className="summary-label">{card.label}</div>
                    </div>
                    <div className={`summary-icon ${card.iconClass}`}>
                      <i className={`fas ${card.icon}`}></i>
                    </div>
                  </div>
                  <div className="summary-meta">{card.meta}</div>
                </div>
              ))}
            </div>

            <div className="rating-overview-grid">
              <section className="rating-panel breakdown-panel">
                <div className="panel-head">
                  <div>
                    <h2 className="section-title">Rating Breakdown</h2>
                    <p className="section-copy">Distribution of all client ratings received so far.</p>
                  </div>
                </div>

                <div className="breakdown-layout">
                  <div className="overall-score-card">
                    <div className="overall-score">{ratingValue.toFixed(1)}</div>
                    <div className="stars-row">{renderStars(ratingValue)}</div>
                    <div className="score-caption">{reviewCount} total reviews</div>
                  </div>

                  <div className="distribution-list">
                    {(overview.distribution || EMPTY_DISTRIBUTION).map(item => (
                      <div key={item.stars} className="distribution-row">
                        <span className="distribution-label">{item.stars} Stars</span>
                        <div className="distribution-bar">
                          <div className="distribution-fill" style={{ width: `${item.percentage || 0}%` }}></div>
                        </div>
                        <span className="distribution-value">{item.count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </section>

              <aside className="rating-panel reputation-panel">
                <h2 className="section-title">Reputation Snapshot</h2>
                <p className="reputation-note">{reputationNote}</p>

                <div className="snapshot-list">
                  <div className="snapshot-item">
                    <span className="snapshot-label">Completed Jobs</span>
                    <strong>{profileStats.total_jobs || 0}</strong>
                  </div>
                  <div className="snapshot-item">
                    <span className="snapshot-label">Lifetime Earnings</span>
                    <strong>{formatMoney(profileStats.total_earnings)}</strong>
                  </div>
                  <div className="snapshot-item">
                    <span className="snapshot-label">Positive Reviews</span>
                    <strong>{positiveShare}%</strong>
                  </div>
                  <div className="snapshot-item">
                    <span className="snapshot-label">Last Updated</span>
                    <strong>{lastUpdated || 'Just now'}</strong>
                  </div>
                </div>
              </aside>
            </div>

            <section className="rating-panel reviews-panel">
              <div className="panel-head">
                <div>
                  <h2 className="section-title">Recent Customer Reviews</h2>
                  <p className="section-copy">Latest delivery feedback from clients who completed transport orders with you.</p>
                </div>
                <div className="review-filters">
                  {[
                    { key: 'all', label: 'All' },
                    { key: '5', label: '5 Star' },
                    { key: '4', label: '4 Star' },
                    { key: 'written', label: 'Written' },
                  ].map(filter => (
                    <button
                      key={filter.key}
                      type="button"
                      className={`filter-chip${reviewFilter === filter.key ? ' active' : ''}`}
                      onClick={() => setReviewFilter(filter.key)}
                    >
                      {filter.label}
                    </button>
                  ))}
                </div>
              </div>

              {filteredReviews.length ? (
                <div className="reviews-grid">
                  {filteredReviews.map(review => (
                    <article className="review-card" key={review.id || `${review.customer_name}-${review.created_at}`}>
                      <div className="review-head">
                        <div className="reviewer-chip">
                          <div className="reviewer-avatar">{initials(review.customer_name)}</div>
                          <div>
                            <h3>{review.customer_name || 'Client'}</h3>
                            <p>{review.customer_location || 'Pakistan'}</p>
                          </div>
                        </div>

                        <div className="review-meta">
                          <div className="stars-row small">{renderStars(review.rating)}</div>
                          <span>{formatDate(review.created_at)}</span>
                        </div>
                      </div>

                      <div className="review-ref">
                        <span>{review.order_reference || `Order #${review.job_id || '--'}`}</span>
                      </div>

                      <p className="review-text">
                        {String(review.review || '').trim() || 'Client left a star rating without written feedback.'}
                      </p>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="empty-state">
                  <i className="fas fa-star-half-alt"></i>
                  <p>No reviews match the selected filter yet.</p>
                </div>
              )}
            </section>

            <div className="rating-analytics-grid">
              <section className="rating-panel trend-panel">
                <div className="panel-head">
                  <div>
                    <h2 className="section-title">Monthly Rating Trend</h2>
                    <p className="section-copy">{trendSummary}</p>
                  </div>
                </div>

                <div className="trend-bars">
                  {(overview.trends || []).map(point => (
                    <div key={point.key || point.month} className="trend-bar">
                      <div className="trend-bar-value">{parseFloat(point.rating || 0).toFixed(1)}</div>
                      <div className="trend-bar-track">
                        <div
                          className="trend-bar-fill"
                          style={{ height: `${Math.max((parseFloat(point.rating || 0) / 5) * 160, 12)}px` }}
                        ></div>
                      </div>
                      <div className="trend-bar-label">{point.month}</div>
                      <div className="trend-bar-count">{point.count || 0} reviews</div>
                    </div>
                  ))}
                </div>
              </section>

              <section className="rating-panel leaderboard-panel">
                <div className="panel-head">
                  <div>
                    <h2 className="section-title">Leaderboard Preview</h2>
                    <p className="section-copy">Where your transporter profile stands compared with other active transporters.</p>
                  </div>
                </div>

                <div className="podium-grid">
                  {(leaderboard.podium || []).length ? (
                    leaderboard.podium.slice(0, 3).map(entry => (
                      <div
                        key={entry.transporter_id || entry.rank}
                        className={`podium-card${entry.is_current_user ? ' current' : ''}`}
                      >
                        <div className="podium-rank">#{entry.rank}</div>
                        <h3>{entry.transporter_name}{entry.is_current_user ? ' (You)' : ''}</h3>
                        <div className="podium-rating">{parseFloat(entry.rating || 0).toFixed(2)}</div>
                        <p>{entry.review_count || 0} reviews</p>
                      </div>
                    ))
                  ) : (
                    <div className="empty-state compact">
                      <i className="fas fa-trophy"></i>
                      <p>Leaderboard data is not available yet.</p>
                    </div>
                  )}
                </div>

                <div className="nearby-section">
                  <h3 className="nearby-title">Nearby Rankings</h3>
                  <div className="nearby-list">
                    {(leaderboard.nearby || []).length ? (
                      leaderboard.nearby.map(entry => (
                        <div
                          key={`nearby-${entry.transporter_id || entry.rank}`}
                          className={`nearby-row${entry.is_current_user ? ' current' : ''}`}
                        >
                          <div>
                            <strong>#{entry.rank} {entry.transporter_name}{entry.is_current_user ? ' (You)' : ''}</strong>
                            <p>{entry.review_count || 0} reviews and {entry.completion_rate || 0}% completion</p>
                          </div>
                          <span>{parseFloat(entry.rating || 0).toFixed(2)}</span>
                        </div>
                      ))
                    ) : (
                      <div className="empty-state compact">
                        <i className="fas fa-chart-line"></i>
                        <p>Your ranking will appear here once review data is available.</p>
                      </div>
                    )}
                  </div>
                </div>
              </section>
            </div>
          </>
        )}

        <div className="footer">
          <p>&copy; 2026 Digi_TransX Transport Services. All rights reserved.</p>
          <div className="footer-links">
            <Link to="/transporter/about">About Us</Link>
            <Link to="/transporter/contact">Contact</Link>
            <Link to="/transporter/terms">Terms &amp; Conditions</Link>
            <Link to="/transporter/privacy">Privacy Policy</Link>
            <Link to="/transporter/help">Help Center</Link>
            <Link to="/transporter/partner">Partner With Us</Link>
          </div>
        </div>
      </div>
    </TransporterLayout>
  )
}
