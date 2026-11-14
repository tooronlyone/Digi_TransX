import { useEffect, useRef, useState } from 'react'
import { apiGet, apiSend, formatMoney } from '../client/clientUtils'
import { AUTH_STATUSES, ShellPageSkeleton, useAuthVerification } from '../../auth/AuthVerificationContext'

export default function DriverTrips() {
  const { user, status } = useAuthVerification()
  if (status !== AUTH_STATUSES.VERIFIED || !user?.id) return <ShellPageSkeleton />
  return <OwnedDriverTrips key={String(user.id)} />
}

function OwnedDriverTrips() {
  const mounted = useRef(false)
  const latestRead = useRef(0)
  const [trips, setTrips] = useState([])
  const [contracts, setContracts] = useState([])
  const [loading, setLoading] = useState(true)
  const [actionId, setActionId] = useState(null)
  const [contractActionId, setContractActionId] = useState(null)
  const [msg, setMsg] = useState('')

  function loadData() {
    const read = ++latestRead.current
    setLoading(true)
    Promise.all([
      apiGet('/api/driver/me'),
      apiGet('/api/driver/hire-contracts'),
    ])
      .then(([driverRes, contractsRes]) => {
        if (!mounted.current || read !== latestRead.current) return
        if (driverRes.success) setTrips(driverRes.recent_trips || [])
        if (contractsRes.success) setContracts(contractsRes.contracts || [])
      })
      .catch(error => { if (mounted.current && read === latestRead.current) setMsg(`Error: ${error.message || 'Unable to load trip requests.'}`) })
      .finally(() => { if (mounted.current && read === latestRead.current) setLoading(false) })
  }

  useEffect(() => {
    mounted.current = true
    // Initial remote fetch; the same function exposes loading state on explicit refresh.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData()
    return () => { mounted.current = false }
  }, [])

  async function handleResponse(id, action) {
    setActionId(id)
    try {
      const res = await apiSend(`/api/driver/trips/${id}/respond`, { action })
      if (!mounted.current) return
      if (res.success) {
        setMsg(`Trip ${action === 'accept' ? 'Accepted' : 'Rejected'} successfully!`)
        loadData()
      }
    } catch (err) {
      if (mounted.current) setMsg(`Error: ${err.message}`)
    } finally {
      if (mounted.current) setActionId(null)
    }
  }

  async function handleContractResponse(id, action) {
    setContractActionId(id)
    try {
      const res = await apiSend(`/api/driver/hire-contracts/${id}/respond`, { action })
      if (!mounted.current) return
      if (res.success) {
        setMsg(res.message || `Contract ${action === 'accept' ? 'Accepted' : 'Declined'} successfully!`)
        loadData()
      }
    } catch (err) {
      if (mounted.current) setMsg(`Error: ${err.message}`)
    } finally {
      if (mounted.current) setContractActionId(null)
    }
  }

  return (
    <div>
<p className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm">Temporary Drivers must maintain PKR 10,000 in a frozen security reserve. An abandonment allegation requires investigation and an authorized decision before any approved recovery. Only the Transporter can initiate standard trip cancellation; emergency reporting remains available.</p>
      {/* Permanent Hire Invitations Section */}
      <div className="driver-card" style={{ borderLeft: '4px solid #3b82f6' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <i className="fas fa-handshake" style={{ fontSize: '1.4rem', color: '#2563eb' }}></i>
          <h2 style={{ margin: 0, fontSize: '1.4rem', fontWeight: 800 }}>Permanent Monthly Hire Invitations</h2>
        </div>
        <p style={{ margin: '4px 0 0 0', color: '#64748b' }}>
          Fleet owners can offer you permanent monthly employment with a fixed salary once you build a strong rating.
        </p>

        {contracts.length === 0 ? (
          <p style={{ marginTop: '14px', color: '#64748b', fontSize: '0.9rem' }}>
            No permanent contract invitations right now. Complete freelance trips with high ratings to receive permanent offers!
          </p>
        ) : (
          <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {contracts.map((c) => (
              <div
                key={c.id}
                style={{
                  border: '1px solid #bfdbfe',
                  borderRadius: '10px',
                  padding: '18px',
                  background: '#f0f7ff',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: '16px',
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <strong style={{ fontSize: '1.1rem', color: '#1e3a8a' }}>{c.transporter_name}</strong>
                    <span style={{ fontSize: '0.8rem', background: '#dbeafe', color: '#1d4ed8', padding: '2px 8px', borderRadius: '4px', fontWeight: 700 }}>
                      Monthly Permanent Offer
                    </span>
                  </div>
                  <p style={{ margin: '4px 0 0 0', color: '#334155' }}>
                    Fixed Monthly Salary: <strong style={{ color: '#16a34a', fontSize: '1.1rem' }}>{formatMoney(c.monthly_salary)} / month</strong> &middot; Duration: {c.contract_months} Months
                  </p>
                  <p style={{ margin: '2px 0 0 0', fontSize: '0.85rem', color: '#64748b' }}>
                    Contact: {c.transporter_phone} &middot; {c.transporter_email}
                  </p>
                  {c.terms && (
                    <p style={{ margin: '6px 0 0 0', fontSize: '0.85rem', color: '#475569', fontStyle: 'italic' }}>
                      &quot;{c.terms}&quot;
                    </p>
                  )}
                </div>

                <div>
                  {c.status === 'offered' ? (
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        type="button"
                        disabled={contractActionId === c.id}
                        onClick={() => handleContractResponse(c.id, 'accept')}
                        style={{
                          background: '#16a34a',
                          color: 'white',
                          border: 'none',
                          padding: '10px 18px',
                          borderRadius: '8px',
                          fontWeight: 700,
                          cursor: 'pointer',
                        }}
                      >
                        Accept Permanent Job
                      </button>
                      <button
                        type="button"
                        disabled={contractActionId === c.id}
                        onClick={() => handleContractResponse(c.id, 'decline')}
                        style={{
                          background: '#ef4444',
                          color: 'white',
                          border: 'none',
                          padding: '10px 18px',
                          borderRadius: '8px',
                          fontWeight: 700,
                          cursor: 'pointer',
                        }}
                      >
                        Decline
                      </button>
                    </div>
                  ) : (
                    <span
                      style={{
                        padding: '6px 14px',
                        borderRadius: '9999px',
                        fontWeight: 700,
                        fontSize: '0.85rem',
                        background: c.status === 'active' ? '#dcfce7' : '#f1f5f9',
                        color: c.status === 'active' ? '#166534' : '#64748b',
                      }}
                    >
                      {c.status === 'active' ? 'ACTIVE PERMANENT EMPLOYMENT' : c.status.toUpperCase()}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Per-Trip Requests Section */}
      <div className="driver-card">
        <h1 style={{ margin: 0, fontSize: '1.6rem', fontWeight: 800 }}>Per-Trip Dispatch Requests</h1>
        <p style={{ margin: '4px 0 0 0', color: '#64748b' }}>
          Accept or decline shipment trip invitations. Only your acceptance links a truck and enables smartphone GPS for that trip.
        </p>

        {msg && (
          <div style={{ marginTop: '16px', padding: '12px', background: '#eff6ff', color: '#1e40af', borderRadius: '8px' }}>
            {msg}
          </div>
        )}

        {loading ? (
          <p style={{ marginTop: '20px' }}>Loading requests...</p>
        ) : trips.length === 0 ? (
          <p style={{ marginTop: '20px', color: '#64748b' }}>No trip requests found right now.</p>
        ) : (
          <div style={{ marginTop: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {trips.map((trip) => (
              <div
                key={trip.id}
                style={{
                  border: '1px solid #e2e8f0',
                  borderRadius: '10px',
                  padding: '20px',
                  background: 'white',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: '16px',
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <h3 style={{ margin: 0, fontSize: '1.15rem' }}>Truck: {trip.truck_number}</h3>
                    <span style={{ fontSize: '0.8rem', background: '#f1f5f9', padding: '3px 8px', borderRadius: '6px' }}>
                      {trip.truck_model}
                    </span>
                  </div>
                  <p style={{ margin: '6px 0 0 0', color: '#475569', fontSize: '0.9rem' }}>
                    Transporter: <strong>{trip.transporter_name}</strong> &middot; Phone: {trip.transporter_phone}
                  </p>
                  <p style={{ margin: '4px 0 0 0', color: '#16a34a', fontWeight: 700 }}>
                    Per-Trip Compensation: {formatMoney(trip.offer_amount || 0)}
                  </p>
                  {trip.notes && (
                    <p style={{ margin: '6px 0 0 0', fontSize: '0.85rem', color: '#64748b', fontStyle: 'italic' }}>
                      &quot;{trip.notes}&quot;
                    </p>
                  )}
                </div>

                <div>
                  {trip.status === 'requested' ? (
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        type="button"
                        disabled={actionId === trip.id}
                        onClick={() => handleResponse(trip.id, 'accept')}
                        style={{
                          background: '#16a34a',
                          color: 'white',
                          border: 'none',
                          padding: '10px 18px',
                          borderRadius: '8px',
                          fontWeight: 700,
                          cursor: 'pointer',
                        }}
                      >
                        Accept Trip
                      </button>
                      <button
                        type="button"
                        disabled={actionId === trip.id}
                        onClick={() => handleResponse(trip.id, 'reject')}
                        style={{
                          background: '#ef4444',
                          color: 'white',
                          border: 'none',
                          padding: '10px 18px',
                          borderRadius: '8px',
                          fontWeight: 700,
                          cursor: 'pointer',
                        }}
                      >
                        Reject
                      </button>
                    </div>
                  ) : (
                    <span
                      style={{
                        padding: '6px 14px',
                        borderRadius: '9999px',
                        fontWeight: 700,
                        fontSize: '0.85rem',
                        background: trip.status === 'accepted' ? '#dcfce7' : '#f1f5f9',
                        color: trip.status === 'accepted' ? '#166534' : '#64748b',
                      }}
                    >
                      {trip.status.toUpperCase()}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
