import { useEffect, useState } from 'react'
import logoMarkUrl from '../../assets/brand/logo-mark.svg'

function counter(id, target) {
  const el = document.getElementById(id)
  if (!el) return

  let val = 0
  const step = target / (2000 / 16)
  const timer = window.setInterval(() => {
    val += step
    if (val >= target) {
      val = target
      window.clearInterval(timer)
    }
    el.textContent = Math.floor(val).toLocaleString()
  }, 16)
}

export default function MainPage() {
  const [activeTab, setActiveTab] = useState('client')
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [navScrolled, setNavScrolled] = useState(false)

  useEffect(() => {
    document.documentElement.dataset.dtxPortal = 'intro'
    document.documentElement.dataset.dtxPage = 'intro-main'
    document.body.dataset.dtxPortal = 'intro'
    document.body.dataset.dtxPage = 'intro-main'

    const fontPreconnect = document.createElement('link')
    fontPreconnect.rel = 'preconnect'
    fontPreconnect.href = 'https://fonts.googleapis.com'
    const fontStylesheet = document.createElement('link')
    fontStylesheet.rel = 'stylesheet'
    fontStylesheet.href = 'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap'
    document.head.append(fontPreconnect, fontStylesheet)

    const revealObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry, index) => {
          if (entry.isIntersecting) {
            window.setTimeout(() => entry.target.classList.add('visible'), index * 80)
          }
        })
      },
      { threshold: 0.1 },
    )
    document.querySelectorAll('.reveal').forEach((el) => revealObserver.observe(el))

    const statsObserver = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          counter('s1', 500)
          counter('s2', 12000)
          counter('s3', 35)
          counter('s4', 48)
          statsObserver.disconnect()
        }
      },
      { threshold: 0.5 },
    )
    const statsBar = document.querySelector('.stats-bar')
    if (statsBar) statsObserver.observe(statsBar)

    const updateNavbarShadow = () => {
      setNavScrolled(window.scrollY > 50)
    }
    window.addEventListener('scroll', updateNavbarShadow)

    return () => {
      revealObserver.disconnect()
      statsObserver.disconnect()
      window.removeEventListener('scroll', updateNavbarShadow)
      document.head.removeChild(fontPreconnect)
      document.head.removeChild(fontStylesheet)
      delete document.documentElement.dataset.dtxPortal
      delete document.documentElement.dataset.dtxPage
      delete document.body.dataset.dtxPortal
      delete document.body.dataset.dtxPage
    }
  }, [])

  return (
    <div>
      <nav
        className="navbar"
        id="navbar"
        style={{
          boxShadow: navScrolled ? '0 4px 12px rgba(0, 0, 0, 0.05)' : 'var(--shadow-medium)',
        }}
      >
        <div className="navbar-left">
          <div className="navbar-logo">
            <div className="logo-icon">
              <i className="fas fa-truck" />
            </div>
            <a href="/" className="navbar-brand">Digi_TransX</a>
          </div>
          <img src={logoMarkUrl} alt="Transport Logo" className="transport-logo" />
        </div>

        <div className="navbar-right">
          <ul
            className="nav-links"
            style={mobileNavOpen ? { display: 'flex' } : undefined}
          >
            <li><a href="#how-it-works">How It Works</a></li>
            <li><a href="#features">Features</a></li>
            <li><a href="#for-who">For You</a></li>
          </ul>
          <a href="/login" className="btn-ghost">Login</a>
          <a href="/signup" className="btn-primary-nav">Get Started</a>
          <button
            type="button"
            className="hamburger"
            aria-label="Toggle navigation menu"
            aria-expanded={mobileNavOpen}
            onClick={() => setMobileNavOpen((prev) => !prev)}
          >
            <i className="fas fa-bars" />
          </button>
        </div>
      </nav>

      <section className="hero">
        <div className="hero-content">
          <div className="hero-badge"><span className="dot" /> Now Live in Pakistan 🇵🇰</div>
          <h1 className="hero-title">
            Pakistan&apos;s <span className="accent">Smartest</span>
            <span className="line-2">Transport Platform</span>
          </h1>
          <p className="hero-subtitle">
            Connect clients with trusted transporters. Place orders, track shipments in real time,
            manage your fleet, and grow your logistics business — all in one place.
          </p>
          <div className="hero-cta">
            <a href="/signup?role=client" className="btn-hero-primary">
              <i className="fas fa-box" /> I Need Transport
            </a>
            <a href="/signup?role=transporter" className="btn-hero-secondary">
              <i className="fas fa-truck" /> I&apos;m a Transporter
            </a>
          </div>
        </div>

        <div className="hero-visual">
          <div className="floating-card c1">
            <div className="card-row">
              <div className="cicon ci-orange"><i className="fas fa-truck-moving" /></div>
              <span className="sbadge sb-live">● Live</span>
            </div>
            <div className="clabel">Active Shipment</div>
            <div className="cval">DTX-2026-0142</div>
            <div className="route-row">
              <span className="rdot" style={{ background: 'var(--success)' }} /> Karachi
              <div className="rline" />
              <span className="rdot" style={{ background: 'var(--accent-primary)' }} /> Lahore
            </div>
            <div className="progress-bar"><div className="progress-fill" /></div>
          </div>

          <div className="floating-card c2">
            <div className="card-row">
              <div className="cicon ci-green"><i className="fas fa-wallet" /></div>
              <span className="sbadge sb-blue">This Month</span>
            </div>
            <div className="clabel">Total Earnings</div>
            <div className="cval">Rs. 142,500 <small>+18%</small></div>
          </div>

          <div className="floating-card c3">
            <div className="card-row">
              <div className="cicon ci-blue"><i className="fas fa-clipboard-list" /></div>
              <span className="sbadge sb-pending">Pending</span>
            </div>
            <div className="clabel">New Job Request</div>
            <div className="cval" style={{ fontSize: '16px', marginTop: '4px' }}>Islamabad → Faisalabad</div>
            <div className="route-row" style={{ marginTop: '8px' }}>
              <i className="fas fa-weight-hanging" style={{ color: 'var(--text-muted)' }} />
              <span>12 Tons</span>
              <span style={{ marginLeft: 'auto', color: 'var(--accent-primary)', fontWeight: 700 }}>Rs. 28,000</span>
            </div>
          </div>
        </div>
      </section>

      <div className="stats-bar">
        <div className="stats-grid">
          <div className="stat-item reveal">
            <div className="stat-number"><span id="s1">0</span><span className="acc">+</span></div>
            <div className="stat-label">Active Transporters</div>
          </div>
          <div className="stat-item reveal">
            <div className="stat-number"><span id="s2">0</span><span className="acc">+</span></div>
            <div className="stat-label">Orders Completed</div>
          </div>
          <div className="stat-item reveal">
            <div className="stat-number"><span id="s3">0</span></div>
            <div className="stat-label">Cities Covered</div>
          </div>
          <div className="stat-item reveal">
            <div className="stat-number">Rs.<span id="s4">0</span><span className="acc">M+</span></div>
            <div className="stat-label">Paid to Transporters</div>
          </div>
        </div>
      </div>

      <section className="section" id="how-it-works">
        <span className="section-label reveal">How It Works</span>
        <h2 className="section-title reveal">Simple. Fast. Reliable.</h2>
        <p className="section-subtitle reveal">
          Whether you&apos;re shipping goods or driving trucks, getting started takes less than 5 minutes.
        </p>
        <div className="how-tabs reveal">
          <button
            type="button"
            className={`how-tab${activeTab === 'client' ? ' active' : ''}`}
            onClick={() => setActiveTab('client')}
          >
            For Clients
          </button>
          <button
            type="button"
            className={`how-tab${activeTab === 'transporter' ? ' active' : ''}`}
            onClick={() => setActiveTab('transporter')}
          >
            For Transporters
          </button>
        </div>

        <div className={`steps-panel${activeTab === 'client' ? ' active' : ''}`} id="panel-client">
          <div className="steps-grid">
            <div className="step-card reveal">
              <div className="step-number">01</div>
              <div className="step-icon"><i className="fas fa-user-plus" /></div>
              <div className="step-title">Create Your Account</div>
              <div className="step-desc">Sign up in 2 minutes. Tell us what you ship, your city, and your business type.</div>
            </div>
            <div className="step-card reveal">
              <div className="step-number">02</div>
              <div className="step-icon"><i className="fas fa-box" /></div>
              <div className="step-title">Post Your Order</div>
              <div className="step-desc">Enter pickup location, delivery destination, cargo type and weight. Get matched with verified transporters instantly.</div>
            </div>
            <div className="step-card reveal">
              <div className="step-number">03</div>
              <div className="step-icon"><i className="fas fa-map-marked-alt" /></div>
              <div className="step-title">Track &amp; Receive</div>
              <div className="step-desc">Follow your shipment live from pickup to delivery. Get notifications at every step.</div>
            </div>
          </div>
        </div>

        <div className={`steps-panel${activeTab === 'transporter' ? ' active' : ''}`} id="panel-transporter">
          <div className="steps-grid">
            <div className="step-card reveal">
              <div className="step-number">01</div>
              <div className="step-icon"><i className="fas fa-truck" /></div>
              <div className="step-title">Register Your Fleet</div>
              <div className="step-desc">Add your trucks with type, capacity, and documents. Get verified and go live on the platform.</div>
            </div>
            <div className="step-card reveal">
              <div className="step-number">02</div>
              <div className="step-icon"><i className="fas fa-clipboard-check" /></div>
              <div className="step-title">Accept Jobs</div>
              <div className="step-desc">Browse available shipment orders near you. Accept jobs that match your fleet and route. No middlemen.</div>
            </div>
            <div className="step-card reveal">
              <div className="step-number">03</div>
              <div className="step-icon"><i className="fas fa-wallet" /></div>
              <div className="step-title">Deliver &amp; Earn</div>
              <div className="step-desc">Complete the delivery, update the status, and watch your earnings grow. Withdraw anytime to your bank account.</div>
            </div>
          </div>
        </div>
      </section>

      <section className="section for-who" id="for-who">
        <span className="section-label reveal">Choose Your Path</span>
        <h2 className="section-title reveal">Built for Both Sides</h2>
        <p className="section-subtitle reveal">
          Digi_TransX serves both businesses that need to ship goods and transporters who want to grow their income.
        </p>
        <div className="for-who-grid">
          <div className="for-card reveal">
            <div className="for-card-icon ci-blue2"><i className="fas fa-building" /></div>
            <h3 className="for-card-title">For Clients</h3>
            <p className="for-card-desc">
              Businesses, factories, retailers — anyone who needs to move goods across Pakistan reliably and affordably.
            </p>
            <ul className="feature-list">
              <li><span className="chk chk-blue"><i className="fas fa-check" /></span> Post orders in under 2 minutes</li>
              <li><span className="chk chk-blue"><i className="fas fa-check" /></span> Verified, rated transporters only</li>
              <li><span className="chk chk-blue"><i className="fas fa-check" /></span> Real-time shipment tracking</li>
              <li><span className="chk chk-blue"><i className="fas fa-check" /></span> Digital invoices and payment history</li>
              <li><span className="chk chk-blue"><i className="fas fa-check" /></span> Cancel anytime before pickup</li>
            </ul>
            <a href="/signup?role=client" className="btn-for btn-blue">
              <i className="fas fa-box" /> Start Shipping Now
            </a>
          </div>

          <div className="for-card reveal">
            <div className="for-card-icon ci-orange2"><i className="fas fa-truck" /></div>
            <h3 className="for-card-title">For Transporters</h3>
            <p className="for-card-desc">
              Fleet owners, individual truck owners — grow your business with a steady stream of verified shipment jobs.
            </p>
            <ul className="feature-list">
              <li><span className="chk chk-orange"><i className="fas fa-check" /></span> Manage your entire fleet in one place</li>
              <li><span className="chk chk-orange"><i className="fas fa-check" /></span> Browse &amp; accept jobs instantly</li>
              <li><span className="chk chk-orange"><i className="fas fa-check" /></span> Track earnings and wallet balance</li>
              <li><span className="chk chk-orange"><i className="fas fa-check" /></span> Build your rating and reputation</li>
              <li><span className="chk chk-orange"><i className="fas fa-check" /></span> Department &amp; team access control</li>
            </ul>
            <a href="/signup?role=transporter" className="btn-for btn-orange">
              <i className="fas fa-truck" /> Register Your Fleet
            </a>
          </div>
        </div>
      </section>

      <section className="section" id="features">
        <span className="section-label reveal">Platform Features</span>
        <h2 className="section-title reveal">Everything You Need</h2>
        <p className="section-subtitle reveal">
          A complete logistics management system built specifically for Pakistan&apos;s transport industry.
        </p>
        <div className="features-grid">
          <div className="feature-card reveal">
            <div className="feature-icon"><i className="fas fa-map-marked-alt" /></div>
            <div className="feature-title">Live Shipment Tracking</div>
            <div className="feature-desc">Follow every shipment from pickup to delivery with real-time status updates and location checkpoints.</div>
          </div>
          <div className="feature-card reveal">
            <div className="feature-icon"><i className="fas fa-shield-alt" /></div>
            <div className="feature-title">Verified Transporters</div>
            <div className="feature-desc">All transporters are verified with CNIC, license, and truck documents before they can accept jobs.</div>
          </div>
          <div className="feature-card reveal">
            <div className="feature-icon"><i className="fas fa-wallet" /></div>
            <div className="feature-title">Digital Payments (PKR)</div>
            <div className="feature-desc">Transparent pricing, automatic commission, and digital invoices — all in Pakistani Rupees.</div>
          </div>
          <div className="feature-card reveal">
            <div className="feature-icon"><i className="fas fa-sitemap" /></div>
            <div className="feature-title">Organization System</div>
            <div className="feature-desc">Manage your transport company with departments, team members, and role-based access control.</div>
          </div>
          <div className="feature-card reveal">
            <div className="feature-icon"><i className="fas fa-star" /></div>
            <div className="feature-title">Ratings &amp; Reviews</div>
            <div className="feature-desc">Build trust with a transparent rating system. Top-rated transporters get priority job visibility.</div>
          </div>
        </div>
      </section>

      <section className="cta-section">
        <div className="cta-box reveal">
          <h2 className="cta-title">Ready to Transform<br /><span>Your Logistics?</span></h2>
          <p className="cta-subtitle">
            Join Pakistan&apos;s growing network of businesses and transporters. Sign up free — no credit card required.
          </p>
          <div className="cta-buttons">
            <a href="/signup?role=client" className="btn-hero-primary">
              <i className="fas fa-box" /> I Need Transport
            </a>
            <a href="/signup?role=transporter" className="btn-hero-secondary">
              <i className="fas fa-truck" /> I&apos;m a Transporter
            </a>
          </div>
        </div>
      </section>

      <footer>
        <div className="footer-top">
          <div className="footer-brand">
            <a href="/" className="navbar-logo" style={{ display: 'inline-flex', marginBottom: '10px', textDecoration: 'none' }}>
              <div className="logo-icon"><i className="fas fa-truck" /></div>
              <span className="navbar-brand">Digi_TransX</span>
            </a>
            <p>Pakistan&apos;s smart transport and logistics platform. Connecting clients with trusted transporters since 2026.</p>
          </div>
          <div className="footer-col">
            <h4>Platform</h4>
            <ul>
              <li><a href="#how-it-works">How It Works</a></li>
              <li><a href="#features">Features</a></li>
              <li><a href="#for-who">For Clients</a></li>
              <li><a href="#for-who">For Transporters</a></li>
            </ul>
          </div>
          <div className="footer-col">
            <h4>Company</h4>
            <ul>
              <li><a href="#how-it-works">About Us</a></li>
              <li><a href="/login">Sign In</a></li>
              <li><a href="#for-who">Help Center</a></li>
            </ul>
          </div>
          <div className="footer-col">
            <h4>Legal</h4>
            <ul>
              <li><a href="/signup">Create Account</a></li>
              <li><a href="/reset-password">Account Recovery</a></li>
            </ul>
          </div>
        </div>
        <div className="footer-bottom">
          <p>© 2026 Digi_TransX Transport Services. All rights reserved.</p>
          <p>Built for <a href="#top">Pakistan 🇵🇰</a></p>
        </div>
      </footer>
    </div>
  )
}
