import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'

export default function ServiceHistory() {
  const { id } = useParams()
  const api = useApi()
  const [truck, setTruck] = useState(null)
  const [records, setRecords] = useState([])
  const [fuelHistory, setFuelHistory] = useState([])
  const [loading, setLoading] = useState(true)

  function load() {
    setLoading(true)

    const truckReq = id ? api.get(`/api/trucks/${id}`) : Promise.resolve(null)
    const maintReq = id
      ? api.get(`/api/trucks/${id}/maintenance`).catch(() => api.get('/api/maintenance'))
      : api.get('/api/maintenance')
    const fuelReq = id
      ? api.get(`/api/trucks/${id}/fuel`).catch(() => api.get('/api/fuel'))
      : api.get('/api/fuel')

    Promise.allSettled([truckReq, maintReq, fuelReq]).then(([truckRes, maintRes, fuelRes]) => {
      if (truckRes.status === 'fulfilled' && truckRes.value) {
        setTruck(truckRes.value.truck || truckRes.value)
      }

      if (maintRes.status === 'fulfilled') {
        const data = maintRes.value.records || maintRes.value.maintenance || []
        setRecords(id ? data.filter((item) => item.truck === id || item.truck_id === id) : data)
      }

      if (fuelRes.status === 'fulfilled') {
        const data = fuelRes.value.entries || []
        setFuelHistory(id ? data.filter((item) => item.truck === id) : data)
      }
    }).finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [id])

  function exportCSV() {
    if (!records.length) return

    const headers = ['Type', 'Date', 'Cost', 'Provider', 'Status', 'Notes']
    const rows = records.map((record) => [
      record.part_type || record.service_type || '',
      record.date || '',
      record.cost || 0,
      record.provider || '',
      record.status || '',
      (record.notes || '').replace(/,/g, ' '),
    ])

    const csv = [headers, ...rows].map((row) => row.join(',')).join('\n')
    const anchor = document.createElement('a')
    anchor.href = `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`
    anchor.download = `service_history${id ? `_truck_${id}` : ''}.csv`
    anchor.click()
  }

  const lastRecord = records.length > 0
    ? records.reduce((a, b) => (new Date(a.date) > new Date(b.date) ? a : b))
    : null
  const upcomingRecord = records.find((record) => record.status === 'scheduled')
  const totalFuelSpend = fuelHistory.reduce((sum, item) => sum + parseFloat(item.cost || 0), 0)

  function statusBadge(status) {
    const colors = {
      scheduled: '#3b82f6',
      completed: '#22c55e',
      overdue: '#ef4444',
      pending: '#f59e0b',
    }
    const color = colors[status] || '#94a3b8'

    return (
      <span
        style={{
          background: `${color}22`,
          color,
          padding: '2px 10px',
          borderRadius: 20,
          fontSize: 12,
          fontWeight: 600,
          textTransform: 'capitalize',
        }}
      >
        {status || '-'}
      </span>
    )
  }

  return (
      <div className="page-service-history">
        <main className="page">
          <section className="hero">
            <div>
              <h2>{id && truck ? `${truck.truck_number} - ` : ''}Service History</h2>
              <p>{truck?.truck_type || 'All trucks'}</p>
            </div>
            <div className="hero-actions">
              <Link className="btn" to="/transporter/trucks">
                <i className="fas fa-truck"></i> Open Fleet
              </Link>
              <button className="btn-secondary" type="button" onClick={exportCSV} disabled={!records.length}>
                <i className="fas fa-download"></i> Download CSV
              </button>
              {id && (
                <>
                  <Link className="btn-secondary" to={`/transporter/trucks/${id}`}>
                    <i className="fas fa-circle-info"></i> Truck Details
                  </Link>
                  <Link className="btn-secondary" to={`/transporter/trucks/${id}/track`}>
                    <i className="fas fa-location-crosshairs"></i> Tracking
                  </Link>
                </>
              )}
            </div>
          </section>

          {loading ? (
            <div className="truck-state-card">
              <i className="fas fa-spinner fa-spin" style={{ fontSize: 28 }}></i>
            </div>
          ) : (
            <>
              <section className="cards">
                <div className="card">
                  <div className="metric-label">Maintenance Records</div>
                  <div className="metric-value">{records.length}</div>
                  <div className="metric-note">Completed and scheduled services.</div>
                </div>
                <div className="card">
                  <div className="metric-label">Last Service Date</div>
                  <div className="metric-value">{lastRecord?.date || '-'}</div>
                  <div className="metric-note">Most recent recorded service.</div>
                </div>
                <div className="card">
                  <div className="metric-label">Next Service Due</div>
                  <div className="metric-value">{upcomingRecord?.date || '-'}</div>
                  <div className="metric-note">Next planned maintenance date.</div>
                </div>
                <div className="card">
                  <div className="metric-label">Fuel Spend</div>
                  <div className="metric-value">PKR {totalFuelSpend.toLocaleString()}</div>
                  <div className="metric-note">Aggregated from fuel logs.</div>
                </div>
              </section>

              <section className="section">
                <div className="toolbar">
                  <h3>Maintenance Timeline</h3>
                  <div className="summary-pills">
                    <span className="pill">{records.length} records</span>
                    <span className="pill">CSV export uses rows below</span>
                  </div>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr><th>Type</th><th>Date</th><th>Cost</th><th>Provider</th><th>Status</th><th>Notes</th></tr>
                    </thead>
                    <tbody>
                      {records.length === 0 ? (
                        <tr><td colSpan={6} style={{ textAlign: 'center', padding: 24 }}>No maintenance records found</td></tr>
                      ) : records.map((record, index) => (
                        <tr key={record.id || index}>
                          <td>{record.part_type || record.service_type || '-'}</td>
                          <td>{record.date || '-'}</td>
                          <td>PKR {parseFloat(record.cost || 0).toLocaleString()}</td>
                          <td>{record.provider || '-'}</td>
                          <td>{statusBadge(record.status)}</td>
                          <td>{record.notes || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="section">
                <h3>Fuel Activity</h3>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr><th>Date</th><th>Station</th><th>Volume (L)</th><th>Total Cost</th><th>Odometer</th></tr>
                    </thead>
                    <tbody>
                      {fuelHistory.length === 0 ? (
                        <tr><td colSpan={5} style={{ textAlign: 'center', padding: 24 }}>No fuel records found</td></tr>
                      ) : fuelHistory.map((item, index) => (
                        <tr key={item.id || index}>
                          <td>{item.date || '-'}</td>
                          <td>{item.notes?.replace('Station: ', '') || '-'}</td>
                          <td>{item.amount} L</td>
                          <td>PKR {parseFloat(item.cost || 0).toLocaleString()}</td>
                          <td>{item.odometer ? `${item.odometer} km` : '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
        </main>
      </div>
    
  )
}
