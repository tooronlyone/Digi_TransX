import { useEffect, useMemo, useState } from 'react'
import { loadTruckCatalog } from '../../lib/truckCatalog'
import { PrimaryButton, SecondaryButton, StateMessage, apiGet, apiSend, formatMoney } from '../client/clientUtils'
import '../../styles/pages/agreement-bids.css'

function statusPill(status) {
  const value = String(status || 'open').replace(/_/g, ' ')
  return <span className={`agreementbids-status agreementbids-status--${String(status || 'open').toLowerCase()}`}>{value}</span>
}

function formatPostTime(value) {
  if (!value) return 'Time not set'
  const normalized = String(value).includes('T') ? value : String(value).replace(' ', 'T')
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('en-PK', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function routeParts(post) {
  const pickup = post.pickup_location || post.pickupLocation || post.pickup || post.pickup_city || post.pickupCity || ''
  const dropoff = post.dropoff_location || post.dropoffLocation || post.dropoff || post.drop_location || post.drop_city || post.dropCity || ''
  return {
    pickup,
    dropoff,
    hasRoute: Boolean(pickup && dropoff),
  }
}

export default function AgreementBids() {
  const [posts, setPosts] = useState([])
  const [trucks, setTrucks] = useState([])
  const [catalog, setCatalog] = useState([])
  const [selectedPostId, setSelectedPostId] = useState(null)
  const [message, setMessage] = useState('')
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      const [postJson, truckJson, catalogJson] = await Promise.all([
        apiGet('/api/agreements/posts/available'),
        apiGet('/api/trucks'),
        loadTruckCatalog(),
      ])
      setPosts(postJson.posts || [])
      setTrucks(truckJson.trucks || [])
      setCatalog(catalogJson)
    } catch (loadError) {
      setError(loadError.message || 'Unable to load agreement bids.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const selectedPost = useMemo(() => posts.find((post) => post.id === selectedPostId) || null, [posts, selectedPostId])
  const requiredTypes = useMemo(() => new Set((selectedPost?.trucks || []).map((truck) => truck.truck_type)), [selectedPost])
  const eligibleTrucks = useMemo(() => trucks.filter((truck) => truck.status === 'active' && truck.tracking_id && requiredTypes.has(truck.catalog_type_key)), [trucks, requiredTypes])

  function typeName(typeKey) {
    return catalog.find((item) => item.type_key === typeKey)?.display_name || typeKey
  }

  function postTruckTypes(post) {
    const names = (post.trucks || []).map((truck) => truck.truck_type_name || typeName(truck.truck_type)).filter(Boolean)
    return [...new Set(names)].join(', ') || 'Truck type not specified'
  }

  function postMeta(post) {
    return [post.cargo_type, post.service_area_text].filter(Boolean).join(' | ')
  }

  function openBid(post) {
    setSelectedPostId(post.id)
    setMessage('')
    setRows([{ truck_id: '', per_km_rate: '', minimum_monthly_guarantee: '' }])
    setError('')
    setNotice('')
  }

  function updateRow(index, field, value) {
    setRows((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, [field]: value } : row))
  }

  async function submitBid(event) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    setNotice('')
    try {
      await apiSend(`/api/agreements/posts/${selectedPost.id}/bids`, {
        message,
        trucks: rows.map((row) => ({
          truck_id: Number(row.truck_id),
          per_km_rate: Number(row.per_km_rate),
          minimum_monthly_guarantee: Number(row.minimum_monthly_guarantee),
        })),
      })
      setNotice('Agreement bid placed.')
      setSelectedPostId(null)
      await loadData()
    } catch (submitError) {
      setError(submitError.message || 'Unable to submit bid.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="agreementbids-page">
      <div className="agreementbids-page-title">
        <div>
          <h1>Agreement Bids</h1>
          <p>Open long-term posts matching your active GPS-enabled trucks.</p>
        </div>
      </div>
      {loading && <StateMessage type="loading">Loading agreement bids...</StateMessage>}
      {error && <StateMessage type="error">{error}</StateMessage>}
      {notice && <StateMessage type="success">{notice}</StateMessage>}
      {!loading && !error && posts.length === 0 && (
        <div className="agreementbids-empty-state">
          <i className="fas fa-file-signature" aria-hidden="true"></i>
          <p>No matching agreement bids right now.</p>
        </div>
      )}

      <div className="agreementbids-grid">
        {posts.map((post) => (
          <article key={post.id} className="agreementbids-card">
            {(() => {
              const route = routeParts(post)
              return (
                <>
            <div className="agreementbids-card-header">
              <div>
                <h2>{post.title}</h2>
                <p>{postMeta(post)}</p>
              </div>
              {statusPill(post.status)}
            </div>
            <div className="agreementbids-truck-type">
              <i className="fas fa-truck" aria-hidden="true"></i>
              <span>{postTruckTypes(post)}</span>
            </div>
            {route.hasRoute && (
              <div className="agreementbids-route">
                <span className="agreementbids-route-point">{route.pickup}</span>
                <i className="fas fa-arrow-right-long" aria-hidden="true"></i>
                <span className="agreementbids-route-point">{route.dropoff}</span>
              </div>
            )}
            <div className="agreementbids-time">
              <i className="fas fa-clock" aria-hidden="true"></i>
              <span>{formatPostTime(post.created_at || post.updated_at)}</span>
            </div>
            <PrimaryButton type="button" className="agreementbids-place-btn" onClick={() => openBid(post)}>
              <i className="fas fa-gavel" aria-hidden="true"></i>
              Place Bid
            </PrimaryButton>
                </>
              )
            })()}
          </article>
        ))}
      </div>

      {selectedPost && (
        <div className="agreementbids-form-panel">
          <div className="agreementbids-form-header">
            <div>
              <h2>Bid for {selectedPost.title}</h2>
              <p>Select GPS-enabled trucks and set monthly rates.</p>
            </div>
            <SecondaryButton type="button" onClick={() => setSelectedPostId(null)}>Close</SecondaryButton>
          </div>
          <form className="agreementbids-form" onSubmit={submitBid}>
            {rows.map((row, index) => (
              <div key={index} className="agreementbids-row">
                <label className="agreementbids-field">
                  <span>Truck</span>
                  <select value={row.truck_id} onChange={(event) => updateRow(index, 'truck_id', event.target.value)} required>
                    <option value="">Select truck</option>
                    {eligibleTrucks.map((truck) => <option key={truck.id} value={truck.id}>{truck.truck_number} - {truck.truck_type}</option>)}
                  </select>
                </label>
                <label className="agreementbids-field">
                  <span>Per KM rate</span>
                  <input type="number" min="0.01" step="0.01" value={row.per_km_rate} onChange={(event) => updateRow(index, 'per_km_rate', event.target.value)} required />
                </label>
                <label className="agreementbids-field">
                  <span>Monthly minimum</span>
                  <input type="number" min="0.01" step="0.01" value={row.minimum_monthly_guarantee} onChange={(event) => updateRow(index, 'minimum_monthly_guarantee', event.target.value)} required />
                </label>
              </div>
            ))}
            <label className="agreementbids-field agreementbids-field--message">
              <span>Message</span>
              <textarea value={message} onChange={(event) => setMessage(event.target.value)} />
            </label>
            <div className="agreementbids-form-actions">
              <SecondaryButton type="button" onClick={() => setRows((current) => [...current, { truck_id: '', per_km_rate: '', minimum_monthly_guarantee: '' }])}>
                <i className="fas fa-plus" aria-hidden="true"></i>
                Add truck
              </SecondaryButton>
              <PrimaryButton type="submit" disabled={submitting || eligibleTrucks.length === 0}>
                <i className={`fas ${submitting ? 'fa-spinner fa-spin' : 'fa-paper-plane'}`} aria-hidden="true"></i>
                Submit bid
              </PrimaryButton>
              {eligibleTrucks.length === 0 && <span className="agreementbids-warning">No eligible GPS-enabled truck for this post.</span>}
            </div>
          </form>
        </div>
      )}
    </div>
  )
}
