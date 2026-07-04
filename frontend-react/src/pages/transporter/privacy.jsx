import { useEffect } from 'react'
import { Link } from 'react-router-dom'

const privacyHighlights = [
  {
    icon: 'fas fa-user-shield',
    label: 'Scope',
    value: 'Transporter accounts, fleet operations, jobs, payouts, ratings, and support activity',
  },
  {
    icon: 'fas fa-calendar-days',
    label: 'Last Updated',
    value: 'April 25, 2026',
  },
  {
    icon: 'fas fa-lock',
    label: 'Core Principle',
    value: 'Collect only what helps run transporter workflows, verify activity, and protect the platform',
  },
  {
    icon: 'fas fa-sliders',
    label: 'Your Controls',
    value: 'Profile updates, security settings, support requests, and account management tools',
  },
]

const privacySections = [
  {
    id: 'collection',
    icon: 'fas fa-folder-open',
    title: 'Information We Collect',
    intro:
      'Digi_TransX collects transporter-side information needed to create accounts, run fleet workflows, handle jobs, and maintain secure platform operations.',
    points: [
      'Account details such as your name, business identity, phone number, email address, and login credentials.',
      'Truck and fleet details including vehicle numbers, operating regions, commercial rates, capacity, and uploaded supporting records.',
      'Operational activity such as job applications, active assignments, payout requests, ratings, support messages, and dashboard usage.',
      'Technical data like browser, session, device, IP, timestamps, and activity patterns used for security and reliability review.',
    ],
  },
  {
    id: 'usage',
    icon: 'fas fa-gears',
    title: 'How We Use Transporter Data',
    intro:
      'We use transporter data to keep the portal usable, commercially reliable, and safer for fleet operators, clients, and platform staff.',
    points: [
      'To create and maintain transporter accounts, truck listings, job workflows, and payout processing.',
      'To verify operational activity, detect abuse, investigate disputes, and reduce fraud or duplicate claims.',
      'To improve product features such as analytics, rankings, rating summaries, reporting, and service guidance.',
      'To respond to support requests, compliance needs, legal duties, and platform security incidents.',
    ],
  },
  {
    id: 'sharing',
    icon: 'fas fa-share-nodes',
    title: 'When Data May Be Shared',
    intro:
      'Transporter data is not shared casually, but some operational sharing is necessary to run dispatch, payment, support, and legal workflows.',
    points: [
      'Relevant account and fleet details may be shown to clients or internal teams when needed for jobs and service coordination.',
      'Limited operational data may be shared with payment, verification, hosting, analytics, or support vendors working on behalf of Digi_TransX.',
      'Information may be disclosed where required by law, court order, regulatory process, or credible fraud and safety investigations.',
      'Aggregated or de-identified operational insights may be used for reporting or platform improvement without exposing direct personal identity where practical.',
    ],
  },
  {
    id: 'retention',
    icon: 'fas fa-clock-rotate-left',
    title: 'Retention and Records',
    intro:
      'Some transporter records must remain available beyond a single session because transport operations, payouts, audits, and disputes can take time to resolve.',
    points: [
      'Account history, job records, ratings, payment activity, and support logs may be retained for operational continuity and audit trails.',
      'Inactive accounts may still have certain business records preserved where legal, tax, fraud, or dispute obligations continue.',
      'We may remove or anonymize data when it is no longer reasonably necessary for platform, legal, or security purposes.',
      'Retention periods can vary by record type, risk level, payment status, and compliance requirements.',
    ],
  },
  {
    id: 'security',
    icon: 'fas fa-shield-halved',
    title: 'Security and Access Protection',
    intro:
      'We use administrative, technical, and workflow controls to reduce unauthorized access, misuse, and avoidable data exposure.',
    points: [
      'Authentication flows, session controls, review logging, and account monitoring help protect transporter access.',
      'No system can guarantee absolute security, so you must also protect passwords, OTP channels, and shared business devices.',
      'Suspicious access, fake identity use, or abuse of transporter records may trigger investigation or account restrictions.',
      'If you suspect compromise, contact Digi_TransX promptly so protective steps can be taken early.',
    ],
  },
  {
    id: 'choices',
    icon: 'fas fa-user-gear',
    title: 'Your Choices and Controls',
    intro:
      'Transporters can influence some of the data stored on the platform by keeping information accurate and using available account tools properly.',
    points: [
      'You can update key account, profile, truck, and business information from the transporter portal where editing is available.',
      'You can use settings flows to review security preferences, password changes, and related account controls.',
      'You can contact support to request clarification, correction, or account help where the portal does not expose a direct option.',
      'Deleting visible content from a page does not always remove historical business records needed for audit, payout, or legal reasons.',
    ],
  },
  {
    id: 'communications',
    icon: 'fas fa-envelope-circle-check',
    title: 'Support and Communications',
    intro:
      'Messages sent through contact forms, help flows, ratings, disputes, and support channels may be stored so issues can be followed through properly.',
    points: [
      'We may use your contact information to respond to operational issues, security notices, payment matters, or policy updates.',
      'Support conversations may be reviewed internally to improve quality, resolve escalations, and maintain a defensible service record.',
      'You should avoid sending unnecessary sensitive information that is not relevant to your transporter issue.',
      'Important transporter notices may continue even if you limit optional promotional communications.',
    ],
  },
]

const policyNotes = [
  'This privacy page is written for transporter-side use of Digi_TransX.',
  'Terms of platform conduct, fleet obligations, and payout rules are covered separately in Terms & Conditions.',
  'Questions about data handling, account access, or operational records should be raised through support before a serious dispute develops.',
]

export default function Privacy() {
  useEffect(() => {
    document.title = 'Transporter Privacy Policy - Digi_TransX'
  }, [])

  return (
      <div className="page-privacy">
        <div className="top-bar">
          <div className="page-title">
            <h1>Privacy Policy</h1>
            <p>This transporter-specific privacy page explains what operational and account data Digi_TransX may collect, use, retain, and protect while you use the transporter portal.</p>
          </div>
        </div>

        <div className="privacy-highlights">
          {privacyHighlights.map((item) => (
            <div className="privacy-highlight-card" key={item.label}>
              <div className="privacy-highlight-icon">
                <i className={item.icon}></i>
              </div>
              <div className="privacy-highlight-content">
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            </div>
          ))}
        </div>

        <div className="privacy-layout">
          <aside className="privacy-sidebar">
            <div className="privacy-card privacy-nav-card">
              <h2>Quick Navigation</h2>
              <div className="privacy-nav-list">
                {privacySections.map((section, index) => (
                  <a href={`#${section.id}`} key={section.id}>
                    <span>{String(index + 1).padStart(2, '0')}</span>
                    {section.title}
                  </a>
                ))}
              </div>
            </div>

            <div className="privacy-card privacy-note-card">
              <h3>Policy Notes</h3>
              <ul>
                {policyNotes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
              <div className="privacy-side-actions">
                <Link to="/transporter/terms">View Terms</Link>
                <Link to="/transporter/contact">Contact Support</Link>
              </div>
            </div>
          </aside>

          <div className="privacy-main">
            {privacySections.map((section) => (
              <section className="privacy-card privacy-section" id={section.id} key={section.id}>
                <div className="privacy-section-head">
                  <div className="privacy-section-icon">
                    <i className={section.icon}></i>
                  </div>
                  <div>
                    <h2>{section.title}</h2>
                    <p>{section.intro}</p>
                  </div>
                </div>

                <ul className="privacy-points">
                  {section.points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </section>
            ))}

            <section className="privacy-card privacy-contact-card">
              <div className="privacy-contact-copy">
                <h2>Questions About Data Handling?</h2>
                <p>
                  If you need clarification about transporter account records, support history, operational logs, or
                  access concerns, contact Digi_TransX support before the issue turns into a security or payout dispute.
                </p>
              </div>
              <div className="privacy-contact-actions">
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
      </div>
    
  )
}
