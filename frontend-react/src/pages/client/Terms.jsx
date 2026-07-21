import { useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import PlatformFeesSection from '../../components/common/PlatformFeesSection'

const clientSections = [
  {
    id: 'account-use',
    icon: 'fa-id-badge',
    title: 'Your Account',
    intro:
      'Your Digi_TransX account is personal to you or your business. You are responsible for every booking, agreement and payment made through your login.',
    points: [
      'Keep login credentials, OTP flows, and account recovery channels secure.',
      'Profile, company, and contact information must stay accurate and current.',
      'Report account misuse, impersonation, or suspicious access to Digi_TransX immediately.',
    ],
  },
  {
    id: 'orders-payments',
    icon: 'fa-wallet',
    title: 'Orders, Payments and Fees',
    intro:
      'Bookings are paid through your platform wallet. The platform fee that applies to each order or agreement is shown in the Platform Fees section above.',
    points: [
      'The commission for a one-time order is locked in when you accept a bid; it never changes afterwards.',
      'The commission for an agreement is locked in when the agreement is finalized and applies to every monthly payment for its full duration.',
      'Keep a sufficient wallet balance for scheduled payments — failed agreement payments can incur late penalties.',
      'Completed payments, invoices and payouts are never recalculated retroactively when platform fees change.',
    ],
  },
  {
    id: 'disputes',
    icon: 'fa-triangle-exclamation',
    title: 'Cancellations and Disputes',
    intro:
      'Use cancellation and dispute channels only for genuine issues involving timing, delivery, payment, or goods handling.',
    points: [
      'Provide supporting facts and documents when contesting a delivery, charge, or trip distance.',
      'Digi_TransX may temporarily hold a payment or request verification during an investigation.',
      'Frequent avoidable cancellations may reduce trust signals or trigger an account review.',
    ],
  },
  {
    id: 'conduct',
    icon: 'fa-shield-halved',
    title: 'Compliance and Conduct',
    intro:
      'Use the platform lawfully and professionally. Bookings must not involve illegal cargo, fraudulent activity, or fake identities.',
    points: [
      'Follow applicable transport, safety, and tax laws in your region.',
      'Harassment, threats, or abuse of transporters or support staff is not allowed.',
      'Platform access may be limited or removed where legal or safety risk becomes unacceptable.',
    ],
  },
]

export default function ClientTerms() {
  useEffect(() => {
    document.title = 'Terms & Platform Fees - Digi_TransX'
  }, [])

  const audience = useMemo(() => {
    try {
      const user = JSON.parse(sessionStorage.getItem('user') || 'null')
      return String(user?.role || '').trim().toLowerCase() === 'everyday_user' ? 'everyday' : 'client'
    } catch {
      return 'client'
    }
  }, [])

  return (
    <div className="page-terms">
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800, color: '#0f172a' }}>Terms &amp; Platform Fees</h1>
        <p style={{ color: '#64748b', fontSize: 14, marginTop: 6 }}>
          These terms govern how your bookings, agreements, payments and account activity work on Digi_TransX.
          The fee section below always shows the currently approved commission rates.
        </p>
      </div>

      <PlatformFeesSection audience={audience} />

      {clientSections.map((section) => (
        <section
          key={section.id}
          id={section.id}
          style={{
            background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 14,
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)', padding: 24, marginBottom: 20,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
            <div style={{
              width: 40, height: 40, borderRadius: 10, background: '#eff6ff', flexShrink: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#2563eb',
            }}>
              <i className={`fas ${section.icon}`} aria-hidden="true"></i>
            </div>
            <div>
              <h2 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: '#0f172a' }}>{section.title}</h2>
              <p style={{ fontSize: 13, color: '#64748b', margin: '6px 0 0' }}>{section.intro}</p>
            </div>
          </div>
          <ul style={{ margin: '14px 0 0', paddingLeft: 22, color: '#475569', fontSize: 14, lineHeight: 1.7 }}>
            {section.points.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        </section>
      ))}

      <section style={{
        background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 14,
        padding: 24, marginBottom: 20, display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', gap: 14, flexWrap: 'wrap',
      }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: '#0f172a' }}>Questions about these terms?</h2>
          <p style={{ fontSize: 13, color: '#64748b', margin: '6px 0 0' }}>
            Reach out through Messages before accepting a bid or finalizing an agreement if anything is unclear.
          </p>
        </div>
        <Link
          to="/client/messages"
          style={{
            background: 'linear-gradient(135deg,#2563eb,#3b82f6)', color: '#fff',
            padding: '10px 18px', borderRadius: 10, fontWeight: 600, fontSize: 13, textDecoration: 'none',
          }}
        >
          <i className="fas fa-comments" aria-hidden="true" style={{ marginRight: 8 }}></i>
          Contact Support
        </Link>
      </section>
    </div>
  )
}
