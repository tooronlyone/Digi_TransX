import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import TransporterLayout from '../../components/transporter/TransporterLayout'

const termHighlights = [
  {
    icon: 'fas fa-file-signature',
    label: 'Applies To',
    value: 'Transporter accounts, fleet listings, rates, jobs, and payouts',
  },
  {
    icon: 'fas fa-calendar-check',
    label: 'Effective Date',
    value: 'April 25, 2026',
  },
  {
    icon: 'fas fa-scale-balanced',
    label: 'Primary Focus',
    value: 'Operational conduct, payment handling, compliance, and platform use',
  },
  {
    icon: 'fas fa-headset',
    label: 'Support Path',
    value: 'Use Contact or Help Center for clarifications before accepting risky jobs',
  },
]

const termSections = [
  {
    id: 'account-use',
    icon: 'fas fa-id-badge',
    title: 'Transporter Account Use',
    intro:
      'Your transporter account is for business use on behalf of your fleet or dispatch operation. You are responsible for every action performed through your login.',
    points: [
      'Keep login credentials, OTP flows, and account recovery channels secure.',
      'Do not share access with unauthorized staff, third parties, or competing operators.',
      'Profile, company, and contact information must stay accurate and current.',
      'If account misuse, impersonation, or suspicious access occurs, report it to Digi_TransX immediately.',
    ],
  },
  {
    id: 'fleet-data',
    icon: 'fas fa-truck-moving',
    title: 'Truck Listings and Fleet Data',
    intro:
      'Every truck record published through the transporter portal must reflect the real operating condition and commercial configuration of that truck.',
    points: [
      'Truck number, chassis details, capacity, type, service regions, and pricing must be truthful.',
      'Insurance, permits, route permissions, and supporting documents must be valid where required.',
      'Inactive, unavailable, or restricted trucks should not be presented as ready for dispatch.',
      'You remain responsible for drivers, subcontracted operators, and fleet partners linked to your listings.',
    ],
  },
  {
    id: 'jobs-operations',
    icon: 'fas fa-route',
    title: 'Job Acceptance and Operational Obligations',
    intro:
      'When you apply for, accept, or continue a job on Digi_TransX, you commit to reasonable operational performance for that assignment.',
    points: [
      'Review route, goods type, timing, pricing, and operational risk before accepting any job.',
      'Pickup, transit, delivery, and status updates must be handled honestly and without fabricated progress.',
      'Delays, incidents, routing changes, or truck substitutions should be communicated promptly through the platform or support flow.',
      'Repeated no-shows, false confirmations, or dispatch misrepresentation may lead to account restrictions.',
    ],
    note:
      'If a job becomes unsafe, illegal, or commercially impossible, escalate it early instead of letting the assignment silently fail.',
  },
  {
    id: 'pricing-payments',
    icon: 'fas fa-wallet',
    title: 'Pricing, Payouts, and Fees',
    intro:
      'Commercial pricing shown through your truck configurations and accepted jobs should be deliberate, supportable, and consistent with the work being offered.',
    points: [
      'Per-km pricing, waiting charges, loading charges, and extra commercial terms should be set before dispatch wherever possible.',
      'Completed jobs may be reviewed before payout release, especially when disputes, cancellations, or missing proof exist.',
      'Withdrawals, processing windows, and deductions depend on available balance, verification state, and platform rules in force at the time.',
      'You must not manipulate job flow, duplicate claims, or misuse payout workflows to create artificial earnings.',
    ],
  },
  {
    id: 'cancellations-disputes',
    icon: 'fas fa-triangle-exclamation',
    title: 'Cancellations, Claims, and Disputes',
    intro:
      'Transport operations can fail for real reasons, but misuse of cancellation or dispute channels damages the platform for everyone.',
    points: [
      'Only raise disputes where there is a genuine issue involving timing, delivery, payment, route, goods handling, or platform misuse.',
      'Provide supporting facts, references, and documents when contesting a charge, job status, or payout decision.',
      'Frequent avoidable cancellations or careless bid behavior may reduce trust signals or trigger account review.',
      'Digi_TransX may temporarily hold payment, limit visibility, or request additional verification during investigations.',
    ],
  },
  {
    id: 'compliance-conduct',
    icon: 'fas fa-shield-halved',
    title: 'Compliance, Safety, and Conduct',
    intro:
      'You must use the transporter portal lawfully, professionally, and in a way that does not expose clients, drivers, or the platform to avoidable harm.',
    points: [
      'Follow applicable transport, labor, safety, tax, and cargo laws in your operating regions.',
      'Do not use Digi_TransX for illegal cargo, fraudulent bookings, fake identities, or prohibited route activity.',
      'Harassment, threats, bribery, abuse of support staff, or abusive client interactions are not allowed.',
      'Platform access may be limited or removed where legal, reputational, or safety risk becomes unacceptable.',
    ],
  },
  {
    id: 'data-records',
    icon: 'fas fa-database',
    title: 'Platform Data and Operational Records',
    intro:
      'Operational records inside Digi_TransX help support dispatch coordination, audit trails, service reliability, and dispute resolution.',
    points: [
      'Truck updates, job history, ratings, communication records, and account activity may be retained for operational review.',
      'Analytics, ranking, rating, or predictive features may rely on the quality of your submitted operational data.',
      'You should not scrape, copy, reverse engineer, or republish protected platform data without authorization.',
      'Operational records may be used for fraud checks, service quality review, audit support, and compliance monitoring.',
    ],
  },
  {
    id: 'changes-enforcement',
    icon: 'fas fa-gavel',
    title: 'Updates, Suspension, and Enforcement',
    intro:
      'Digi_TransX may revise transporter terms as the portal, business model, compliance requirements, and operational controls evolve.',
    points: [
      'Updated terms can apply to future platform use after publication or notice, depending on the change type.',
      'Accounts may be warned, restricted, suspended, or removed for serious or repeated violations.',
      'Nothing in these terms guarantees uninterrupted service, guaranteed job volume, or guaranteed earnings.',
      'If you do not agree with updated transporter terms, stop using the transporter portal and contact support for closure guidance.',
    ],
  },
]

const changeHistory = [
  {
    version: 'v3.2',
    date: 'April 25, 2026',
    summary: 'Clarified payout review, cancellation handling, and transporter-side dispute expectations.',
  },
  {
    version: 'v3.1',
    date: 'January 14, 2026',
    summary: 'Expanded truck data accuracy and document responsibility language for active fleet listings.',
  },
  {
    version: 'v3.0',
    date: 'September 08, 2025',
    summary: 'Aligned transporter terms with the modern Digi_TransX portal and operational dashboard modules.',
  },
]

export default function Terms() {
  useEffect(() => {
    document.title = 'Transporter Terms & Conditions - Digi_TransX'
  }, [])

  return (
    <TransporterLayout>
      <div className="page-terms">
        <div className="top-bar">
          <div className="page-title">
            <h1>Terms &amp; Conditions</h1>
            <p>These transporter-specific terms govern how your fleet, jobs, payments, ratings, and account activity are used on Digi_TransX.</p>
          </div>
        </div>

        <div className="terms-highlights">
          {termHighlights.map((item) => (
            <div className="highlight-card" key={item.label}>
              <div className="highlight-icon">
                <i className={item.icon}></i>
              </div>
              <div className="highlight-content">
                <span className="highlight-label">{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            </div>
          ))}
        </div>

        <div className="terms-layout">
          <aside className="terms-sidebar">
            <div className="terms-card terms-nav-card">
              <h2>Quick Navigation</h2>
              <div className="terms-nav-list">
                {termSections.map((section, index) => (
                  <a href={`#${section.id}`} key={section.id}>
                    <span>{String(index + 1).padStart(2, '0')}</span>
                    {section.title}
                  </a>
                ))}
              </div>
            </div>

            <div className="terms-card terms-side-note">
              <h3>Important</h3>
              <p>
                Continuing to use the transporter portal means you agree to follow these transporter-side terms for
                account access, fleet listings, jobs, payments, and operational conduct.
              </p>
              <div className="terms-side-actions">
                <Link to="/transporter/contact">Contact Support</Link>
                <Link to="/transporter/help">Visit Help Center</Link>
              </div>
            </div>
          </aside>

          <div className="terms-main">
            {termSections.map((section) => (
              <section className="terms-card terms-section" id={section.id} key={section.id}>
                <div className="section-heading">
                  <div className="section-icon">
                    <i className={section.icon}></i>
                  </div>
                  <div>
                    <h2>{section.title}</h2>
                    <p>{section.intro}</p>
                  </div>
                </div>

                <ul className="terms-points">
                  {section.points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>

                {section.note ? <div className="terms-note">{section.note}</div> : null}
              </section>
            ))}

            <section className="terms-card terms-history">
              <div className="history-head">
                <h2>Version History</h2>
                <span>Transporter-side legal summary</span>
              </div>

              <div className="history-list">
                {changeHistory.map((item) => (
                  <div className="history-item" key={item.version}>
                    <div className="history-version">{item.version}</div>
                    <div className="history-date">{item.date}</div>
                    <p>{item.summary}</p>
                  </div>
                ))}
              </div>
            </section>

            <section className="terms-card terms-support">
              <div className="support-copy">
                <h2>Need Clarification Before Dispatch?</h2>
                <p>
                  If any transporter term affects how you price, accept, deliver, or dispute jobs, review the Help
                  Center or contact support before taking action that could create a compliance or payout issue.
                </p>
              </div>
              <div className="support-actions">
                <Link className="primary-link" to="/transporter/contact">
                  <i className="fas fa-headset"></i>
                  Contact Support
                </Link>
                <Link className="secondary-link" to="/transporter/help">
                  <i className="fas fa-circle-question"></i>
                  Help Center
                </Link>
              </div>
            </section>
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
