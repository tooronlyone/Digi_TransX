import { useEffect, useState } from 'react'
import OrgActivityFeed from '../../../components/org/OrgActivityFeed'
import OrgShell from '../../../components/org/OrgShell'
import { orgAuthRequest } from '../../../lib/orgPortal'

export default function OrgPartnerActivity() {
  const [banner, setBanner] = useState(null)
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    setBanner(null)
    try {
      const response = await orgAuthRequest('/api/org/activity?limit=50', { method: 'GET' })
      setRows(response.activity || [])
    } catch (error) {
      setRows([])
      setBanner({ type: 'error', message: error.message || 'Unable to load activity.' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  return (
    <OrgShell
      title="Activity Logs"
      subtitle="Department-scoped audit trail based on your assigned partner permissions."
      banner={banner}
      actions={<a className="org-link" href="/org/partner/dashboard">Back</a>}
    >
      <section className="org-card">
        <div className="org-row spread" style={{ marginBottom: 14 }}>
          <div className="org-hint">Most recent events (limit 50)</div>
          <button type="button" className="org-button secondary" onClick={load}>
            Refresh
          </button>
        </div>
        {loading ? (
          <div className="org-empty-state">
            <i className="fas fa-spinner fa-spin"></i>
            <div>Loading activity...</div>
          </div>
        ) : (
          <OrgActivityFeed rows={rows} />
        )}
      </section>
    </OrgShell>
  )
}
