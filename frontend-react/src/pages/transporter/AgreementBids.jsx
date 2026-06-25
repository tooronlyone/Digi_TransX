import { useEffect, useMemo, useState } from 'react'
import { loadTruckCatalog } from '../../lib/truckCatalog'
import { PrimaryButton, SecondaryButton, StateMessage, StatusBadge, apiGet, apiSend, formatMoney } from '../client/clientUtils'

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
    <div className="space-y-6">
      <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900">Agreement Bids</h1>
        <p className="mt-1 text-sm text-slate-500">Open long-term posts matching your active GPS-enabled trucks.</p>
      </div>
      {loading && <StateMessage type="loading">Loading agreement bids...</StateMessage>}
      {error && <StateMessage type="error">{error}</StateMessage>}
      {notice && <StateMessage type="success">{notice}</StateMessage>}
      {!loading && !error && posts.length === 0 && <StateMessage type="empty">No matching agreement bids right now.</StateMessage>}

      <div className="grid gap-4 xl:grid-cols-2">
        {posts.map((post) => (
          <article key={post.id} className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold text-slate-900">{post.title}</h2>
                <p className="mt-1 text-sm text-slate-500">{post.cargo_type} | {post.service_area_text}</p>
              </div>
              <StatusBadge status={post.status} />
            </div>
            <div className="mt-4 grid gap-2 text-sm text-slate-600">
              {(post.trucks || []).map((truck) => (
                <div key={truck.id}>{typeName(truck.truck_type)} | {truck.capacity_tons} tons | Qty {truck.quantity}</div>
              ))}
            </div>
            <PrimaryButton type="button" className="mt-4" onClick={() => openBid(post)}>
              <i className="fas fa-gavel" aria-hidden="true"></i>
              Place Bid
            </PrimaryButton>
          </article>
        ))}
      </div>

      {selectedPost && (
        <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-xl font-bold text-slate-900">Bid for {selectedPost.title}</h2>
              <p className="mt-1 text-sm text-slate-500">Select GPS-enabled trucks and set monthly rates.</p>
            </div>
            <SecondaryButton type="button" onClick={() => setSelectedPostId(null)}>Close</SecondaryButton>
          </div>
          <form className="mt-5 grid gap-4" onSubmit={submitBid}>
            {rows.map((row, index) => (
              <div key={index} className="grid gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4 md:grid-cols-3">
                <label className="grid gap-2 text-sm font-medium text-slate-700">
                  Truck
                  <select className="rounded-lg border border-slate-300 px-3 py-2.5" value={row.truck_id} onChange={(event) => updateRow(index, 'truck_id', event.target.value)} required>
                    <option value="">Select truck</option>
                    {eligibleTrucks.map((truck) => <option key={truck.id} value={truck.id}>{truck.truck_number} - {truck.truck_type}</option>)}
                  </select>
                </label>
                <label className="grid gap-2 text-sm font-medium text-slate-700">
                  Per KM rate
                  <input className="rounded-lg border border-slate-300 px-3 py-2.5" type="number" min="0.01" step="0.01" value={row.per_km_rate} onChange={(event) => updateRow(index, 'per_km_rate', event.target.value)} required />
                </label>
                <label className="grid gap-2 text-sm font-medium text-slate-700">
                  Monthly minimum
                  <input className="rounded-lg border border-slate-300 px-3 py-2.5" type="number" min="0.01" step="0.01" value={row.minimum_monthly_guarantee} onChange={(event) => updateRow(index, 'minimum_monthly_guarantee', event.target.value)} required />
                </label>
              </div>
            ))}
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Message
              <textarea className="min-h-24 rounded-lg border border-slate-300 px-3 py-2.5" value={message} onChange={(event) => setMessage(event.target.value)} />
            </label>
            <div className="flex flex-wrap gap-3">
              <SecondaryButton type="button" onClick={() => setRows((current) => [...current, { truck_id: '', per_km_rate: '', minimum_monthly_guarantee: '' }])}>
                <i className="fas fa-plus" aria-hidden="true"></i>
                Add truck
              </SecondaryButton>
              <PrimaryButton type="submit" disabled={submitting || eligibleTrucks.length === 0}>
                <i className={`fas ${submitting ? 'fa-spinner fa-spin' : 'fa-paper-plane'}`} aria-hidden="true"></i>
                Submit bid
              </PrimaryButton>
              {eligibleTrucks.length === 0 && <span className="self-center text-sm text-amber-700">No eligible GPS-enabled truck for this post.</span>}
            </div>
          </form>
        </div>
      )}
    </div>
  )
}
