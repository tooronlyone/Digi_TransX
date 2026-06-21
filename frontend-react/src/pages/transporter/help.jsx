import { useState, useMemo } from 'react'
import TransporterLayout from '../../components/transporter/TransporterLayout'
import { Link } from 'react-router-dom'

const CATEGORIES = [
  { icon: 'fas fa-truck', title: 'Truck Management', desc: 'Add, edit, and manage your trucks', link: '/transporter/trucks' },
  { icon: 'fas fa-briefcase', title: 'Jobs & Bookings', desc: 'Browse and manage shipment jobs', link: '/transporter/jobs' },
  { icon: 'fas fa-rupee-sign', title: 'Payments & Earnings', desc: 'Transactions, withdrawals, and earnings', link: '/transporter/earnings' },
  { icon: 'fas fa-tools', title: 'Fleet Overview', desc: 'Review truck status and service history from active fleet pages', link: '/transporter/trucks' },
  { icon: 'fas fa-gas-pump', title: 'Account History', desc: 'Review payments and historical account entries', link: '/transporter/account-history' },
  { icon: 'fas fa-chart-line', title: 'My Bids', desc: 'Review pending, accepted, and withdrawn bids', link: '/transporter/bids' },
  { icon: 'fas fa-cog', title: 'Account Settings', desc: 'Profile, notifications, and security', link: '/transporter/settings' },
  { icon: 'fas fa-headset', title: 'Contact Support', desc: 'Reach our team for any help', link: '/transporter/contact' },
]

const FAQS = [
  { q: 'How do I add a new truck to my fleet?', a: 'Go to My Trucks → click "Add Truck". Fill in the truck number, type, capacity, and chassis number. Upload the truck photo and insurance document for faster verification.' },
  { q: 'How do I accept an available job?', a: 'Navigate to Jobs → Available Jobs. Browse listings and click "Apply" on any job. Once a service seeker accepts your application, the job appears in Active Jobs.' },
  { q: 'When do I receive payment for completed jobs?', a: 'Payments are processed after job completion and confirmation by the service seeker. Funds appear in your Earnings section and can be withdrawn to your bank account.' },
  { q: 'How do I configure truck pricing?', a: 'Go to My Trucks → select a truck → click Edit/Configure. Enter your per-km rate, waiting charge per hour, and optionally loading/unloading charges to make the truck dispatch-ready.' },
  { q: 'How do I track my truck location?', a: 'Go to My Trucks → select a truck → click Track. If the truck has a tracking device ID configured and an active job, you can view the current status and route progress.' },
  { q: 'What documents are needed for truck activation?', a: 'You need: truck number, truck type, capacity, chassis number, operating provinces, per-km rate, and waiting charge. Truck photo and insurance paper are optional but recommended.' },
  { q: 'How do I update my profile information?', a: 'Go to Profile or Settings → Account section. Update your name, email, phone, and business details. Changes are saved immediately.' },
  { q: 'What is the Predictive Insights feature?', a: 'Predictive Insights uses your historical data — jobs, fuel, maintenance — to forecast earnings for the next 7, 15, 30, and 90 days. It also gives smart recommendations to grow your business.' },
  { q: 'How do I export my transaction history?', a: 'Go to Account History. Use the date filters if needed, then click "Export Excel" to download a CSV file, or "Export PDF" to print the full transaction list.' },
  { q: 'How do I change my password or PIN?', a: 'Go to Settings → Privacy & Security. Click "Change Password" or use the OTP verification flow. An OTP will be sent to your registered email or phone.' },
]

const ARTICLES = [
  { title: 'Getting Started: Setting Up Your Transporter Account', category: 'Account', time: '3 min read' },
  { title: 'How to Add and Configure Your First Truck', category: 'Trucks', time: '5 min read' },
  { title: 'Understanding Job Matching and Fare Calculation', category: 'Jobs', time: '4 min read' },
  { title: 'Tracking Fuel Costs to Maximize Profit', category: 'Fuel', time: '3 min read' },
  { title: 'Maintenance Scheduling Best Practices', category: 'Maintenance', time: '4 min read' },
  { title: 'Reading Your Analytics Dashboard', category: 'Analytics', time: '5 min read' },
]

export default function Help() {
  const [search, setSearch] = useState('')
  const [activeFaq, setActiveFaq] = useState(-1)

  const filteredFaqs = useMemo(() => {
    if (!search.trim()) return FAQS
    const q = search.toLowerCase()
    return FAQS.filter(f => f.q.toLowerCase().includes(q) || f.a.toLowerCase().includes(q))
  }, [search])

  const filteredArticles = useMemo(() => {
    if (!search.trim()) return ARTICLES
    const q = search.toLowerCase()
    return ARTICLES.filter(a => a.title.toLowerCase().includes(q) || a.category.toLowerCase().includes(q))
  }, [search])

  const filteredCategories = useMemo(() => {
    if (!search.trim()) return CATEGORIES
    const q = search.toLowerCase()
    return CATEGORIES.filter(c => c.title.toLowerCase().includes(q) || c.desc.toLowerCase().includes(q))
  }, [search])

  return (
    <TransporterLayout>
      <div className="page-help">
        <div className="page-title">
          <h1>Help Center</h1>
          <p>Find answers to your questions or contact our support team</p>
        </div>

        <div className="search-section">
          <div className="search-box">
            <i className="fas fa-search"></i>
            <input
              type="text"
              placeholder="Search for help articles, FAQs..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {search && (
              <button onClick={() => setSearch('')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)' }}>
                <i className="fas fa-times"></i>
              </button>
            )}
          </div>
          {search && (
            <p style={{ color: 'var(--text-secondary)', marginTop: 8, fontSize: 14 }}>
              Showing results for "<strong>{search}</strong>" — {filteredFaqs.length} FAQs, {filteredArticles.length} articles
            </p>
          )}
        </div>

        <div className="quick-support" style={{ display: 'flex', gap: 16, marginBottom: 32, flexWrap: 'wrap' }}>
          <Link to="/transporter/contact" style={{ flex: 1, minWidth: 200, background: 'var(--primary)', color: '#fff', borderRadius: 10, padding: '16px 20px', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 12 }}>
            <i className="fas fa-headset" style={{ fontSize: 24 }}></i>
            <div><div style={{ fontWeight: 600 }}>Live Support</div><div style={{ fontSize: 13, opacity: 0.85 }}>Chat or call 24/7</div></div>
          </Link>
          <a href="mailto:support@digitransx.com" style={{ flex: 1, minWidth: 200, background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: 10, padding: '16px 20px', textDecoration: 'none', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 12 }}>
            <i className="fas fa-envelope" style={{ fontSize: 24, color: 'var(--primary)' }}></i>
            <div><div style={{ fontWeight: 600 }}>Email Support</div><div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>support@digitransx.com</div></div>
          </a>
        </div>

        {!search && (
          <div className="categories-section">
            <h2 className="section-title">Browse by Category</h2>
            <div className="categories-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 16 }}>
              {CATEGORIES.map(cat => (
                <Link key={cat.title} to={cat.link} style={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: 10, padding: '18px 16px', textDecoration: 'none', color: 'var(--text-primary)', display: 'flex', flexDirection: 'column', gap: 8, transition: 'border-color 0.2s' }}>
                  <i className={cat.icon} style={{ fontSize: 24, color: 'var(--primary)' }}></i>
                  <div style={{ fontWeight: 600 }}>{cat.title}</div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{cat.desc}</div>
                </Link>
              ))}
            </div>
          </div>
        )}

        {search && filteredCategories.length > 0 && (
          <div style={{ marginBottom: 32 }}>
            <h2 className="section-title">Matching Sections</h2>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              {filteredCategories.map(cat => (
                <Link key={cat.title} to={cat.link} style={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: 8, padding: '10px 16px', textDecoration: 'none', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 8 }}>
                  <i className={cat.icon} style={{ color: 'var(--primary)' }}></i> {cat.title}
                </Link>
              ))}
            </div>
          </div>
        )}

        <div className="articles-section" style={{ marginBottom: 32 }}>
          <h2 className="section-title">Help Articles</h2>
          <div className="articles-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16 }}>
            {filteredArticles.length === 0 ? (
              <p style={{ color: 'var(--text-secondary)' }}>No articles match your search.</p>
            ) : filteredArticles.map(art => (
              <div key={art.title} style={{ background: 'var(--card-bg)', border: '1px solid var(--border-color)', borderRadius: 10, padding: '16px 18px' }}>
                <div style={{ fontSize: 12, color: 'var(--primary)', fontWeight: 600, marginBottom: 6, textTransform: 'uppercase' }}>{art.category}</div>
                <div style={{ fontWeight: 600, marginBottom: 8 }}>{art.title}</div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}><i className="fas fa-clock" style={{ marginRight: 4 }}></i>{art.time}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="faqs-section">
          <h2 className="section-title">Frequently Asked Questions</h2>
          <div className="faqs-container" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {filteredFaqs.length === 0 ? (
              <p style={{ color: 'var(--text-secondary)' }}>No FAQs match your search.</p>
            ) : filteredFaqs.map((faq, i) => {
              const isActive = activeFaq === i
              return (
                <div key={faq.q} style={{ background: 'var(--card-bg)', border: `1px solid ${isActive ? 'var(--primary)' : 'var(--border-color)'}`, borderRadius: 10, overflow: 'hidden' }}>
                  <button
                    type="button"
                    onClick={() => setActiveFaq(isActive ? -1 : i)}
                    style={{ width: '100%', padding: '14px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-primary)', textAlign: 'left', fontWeight: 600 }}
                  >
                    <span>{faq.q}</span>
                    <i className={`fas fa-chevron-${isActive ? 'up' : 'down'}`} style={{ color: 'var(--primary)', flexShrink: 0, marginLeft: 8 }}></i>
                  </button>
                  {isActive && (
                    <div style={{ padding: '0 18px 16px', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                      {faq.a}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
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
