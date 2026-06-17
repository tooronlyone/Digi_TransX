import { useState } from 'react'
import TransporterLayout from '../../components/transporter/TransporterLayout'
import { Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'

const BENEFITS = [
  { icon: 'fas fa-briefcase', title: 'Consistent Job Flow', desc: 'Access hundreds of daily shipment requests from verified service seekers across Pakistan.' },
  { icon: 'fas fa-rupee-sign', title: 'Fast Payments', desc: 'Receive earnings directly after job completion with transparent fee structure.' },
  { icon: 'fas fa-chart-line', title: 'Analytics & Insights', desc: 'Use AI-powered predictions and analytics to maximize your fleet utilization and profit.' },
  { icon: 'fas fa-shield-alt', title: 'Verified Clients', desc: 'All service seekers are KYC-verified. No fraud, no fake bookings.' },
  { icon: 'fas fa-headset', title: '24/7 Support', desc: 'Dedicated transporter support via phone, email, and live chat around the clock.' },
  { icon: 'fas fa-brain', title: 'Smart Tools', desc: 'Maintenance scheduling, fuel tracking, route planning, and predictive fleet management.' },
]

const REQUIREMENTS = [
  { icon: 'fas fa-truck', title: 'Valid Truck', desc: 'At least one registered truck with valid documentation' },
  { icon: 'fas fa-id-card', title: 'CNIC Verification', desc: 'Valid national identity card for the account holder' },
  { icon: 'fas fa-file-alt', title: 'Business Registration', desc: 'NTN or business registration document (preferred)' },
  { icon: 'fas fa-phone', title: 'Active Contact', desc: 'Working phone number for dispatch coordination' },
]

const STORIES = [
  { name: 'Ahmed Khan', trucks: 4, city: 'Lahore', story: 'Joined as a single-truck owner. Within 6 months, grew to 4 trucks with consistent weekly jobs.', rating: 5 },
  { name: 'Tariq Logistics', trucks: 12, city: 'Karachi', story: 'Switched from manual bookings to Digi_TransX. Job volume increased by 3x in the first quarter.', rating: 5 },
  { name: 'Malik Transport', trucks: 7, city: 'Faisalabad', story: 'The fuel and maintenance tracking alone saves us PKR 50,000 per month in unnecessary costs.', rating: 5 },
]

const EMPTY_FORM = { full_name: '', business_name: '', city: '', phone: '', email: '', truck_count: '', truck_types: '', message: '' }

export default function PartnerWithUs() {
  const api = useApi()
  const [form, setForm] = useState(EMPTY_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState('')

  function setField(e) {
    const { name, value } = e.target
    setForm(f => ({ ...f, [name]: value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    if (!form.full_name || !form.phone || !form.email || !form.city) {
      setError('Please fill in all required fields.')
      return
    }
    setSubmitting(true)
    try {
      await api.post('/api/partner/apply', form)
      setSubmitted(true)
    } catch {
      setError('Failed to submit application. Please try again or contact us directly.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <TransporterLayout>
      <div className="page-partner-with-us">
        <div className="top-bar">
          <div className="page-title">
            <h1>Partner With Us</h1>
            <p>Join our network of successful transport partners and grow your business</p>
          </div>
        </div>

        <div className="partner-content">
          <section className="partner-section">
            <h2>Why Partner With Digi_TransX?</h2>
            <div className="benefits-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 20, marginTop: 20 }}>
              {BENEFITS.map(b => (
                <div key={b.title} style={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: 12, padding: '20px 18px' }}>
                  <div style={{ width: 44, height: 44, borderRadius: '50%', background: 'var(--primary-light, #e8f4ff)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 14 }}>
                    <i className={b.icon} style={{ color: 'var(--primary)', fontSize: 20 }}></i>
                  </div>
                  <h3 style={{ margin: '0 0 8px', fontSize: 16 }}>{b.title}</h3>
                  <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: 14, lineHeight: 1.5 }}>{b.desc}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="partner-section" style={{ marginTop: 48 }}>
            <h2>Partnership Requirements</h2>
            <div className="requirements-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16, marginTop: 20 }}>
              {REQUIREMENTS.map(r => (
                <div key={r.title} style={{ display: 'flex', gap: 14, padding: '16px', background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: 10 }}>
                  <div style={{ width: 36, height: 36, borderRadius: 8, background: '#d4edda', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <i className={r.icon} style={{ color: '#27ae60', fontSize: 16 }}></i>
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>{r.title}</div>
                    <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{r.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="partner-section" style={{ marginTop: 48 }}>
            <h2>Success Stories</h2>
            <div className="stories-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 20, marginTop: 20 }}>
              {STORIES.map(s => (
                <div key={s.name} style={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: 12, padding: '20px 18px' }}>
                  <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 14 }}>
                    <div style={{ width: 44, height: 44, borderRadius: '50%', background: 'var(--primary)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 18 }}>
                      {s.name[0]}
                    </div>
                    <div>
                      <div style={{ fontWeight: 700 }}>{s.name}</div>
                      <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{s.city} · {s.trucks} trucks</div>
                    </div>
                  </div>
                  <p style={{ margin: '0 0 12px', color: 'var(--text-secondary)', fontSize: 14, lineHeight: 1.6, fontStyle: 'italic' }}>"{s.story}"</p>
                  <div style={{ color: '#f39c12' }}>{'★'.repeat(s.rating)}</div>
                </div>
              ))}
            </div>
          </section>

          <section className="partner-section" style={{ marginTop: 48 }}>
            <div style={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: 16, padding: 32, maxWidth: 600, margin: '0 auto' }}>
              <h2 style={{ marginBottom: 8 }}>Apply to Partner</h2>
              <p style={{ color: 'var(--text-secondary)', marginBottom: 24 }}>Fill in the form below and our team will contact you within 24 hours.</p>

              {submitted ? (
                <div style={{ textAlign: 'center', padding: '32px 0' }}>
                  <i className="fas fa-check-circle" style={{ fontSize: 52, color: '#27ae60', marginBottom: 16 }}></i>
                  <h3 style={{ color: '#27ae60' }}>Application Submitted!</h3>
                  <p style={{ color: 'var(--text-secondary)' }}>Thank you, {form.full_name}. Our partnership team will reach out to {form.email} within 24 hours.</p>
                  <button className="action-btn" style={{ marginTop: 20 }} onClick={() => { setSubmitted(false); setForm(EMPTY_FORM) }}>
                    Submit Another
                  </button>
                </div>
              ) : (
                <form onSubmit={handleSubmit} noValidate>
                  {error && (
                    <div style={{ color: '#e74c3c', background: '#ffeaea', border: '1px solid #e74c3c', borderRadius: 8, padding: '10px 14px', marginBottom: 16, fontSize: 14 }}>
                      <i className="fas fa-exclamation-circle"></i> {error}
                    </div>
                  )}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                    <div className="form-group" style={{ gridColumn: '1' }}>
                      <label>Full Name <span style={{ color: '#e74c3c' }}>*</span></label>
                      <input type="text" name="full_name" value={form.full_name} onChange={setField} placeholder="Your full name" className="form-control" required />
                    </div>
                    <div className="form-group" style={{ gridColumn: '2' }}>
                      <label>Business Name</label>
                      <input type="text" name="business_name" value={form.business_name} onChange={setField} placeholder="Company or trade name" className="form-control" />
                    </div>
                    <div className="form-group">
                      <label>Phone <span style={{ color: '#e74c3c' }}>*</span></label>
                      <input type="tel" name="phone" value={form.phone} onChange={setField} placeholder="03XX-XXXXXXX" className="form-control" required />
                    </div>
                    <div className="form-group">
                      <label>Email <span style={{ color: '#e74c3c' }}>*</span></label>
                      <input type="email" name="email" value={form.email} onChange={setField} placeholder="you@example.com" className="form-control" required />
                    </div>
                    <div className="form-group">
                      <label>City <span style={{ color: '#e74c3c' }}>*</span></label>
                      <input type="text" name="city" value={form.city} onChange={setField} placeholder="Your city" className="form-control" required />
                    </div>
                    <div className="form-group">
                      <label>Number of Trucks</label>
                      <input type="number" name="truck_count" value={form.truck_count} onChange={setField} placeholder="How many trucks?" className="form-control" min="1" />
                    </div>
                    <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                      <label>Truck Types</label>
                      <input type="text" name="truck_types" value={form.truck_types} onChange={setField} placeholder="e.g. Cargo, Oil Tanker, Refrigerated" className="form-control" />
                    </div>
                    <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                      <label>Message (Optional)</label>
                      <textarea name="message" value={form.message} onChange={setField} placeholder="Tell us about your business or any questions..." className="form-control" rows={3}></textarea>
                    </div>
                  </div>
                  <button type="submit" className="action-btn" style={{ width: '100%', marginTop: 8 }} disabled={submitting}>
                    <i className="fas fa-paper-plane"></i> {submitting ? 'Submitting...' : 'Submit Application'}
                  </button>
                </form>
              )}
            </div>
          </section>
        </div>

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
