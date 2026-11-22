import { useEffect } from 'react'

const ABOUT_CONTENT = {
  company: {
    name: 'Digi_TransX',
    tagline: "Pakistan's digital goods transport platform for structured orders, fleet control, payments, and verified delivery.",
    description:
      'Digi_TransX brings transport operations into one practical workspace. The V1 platform connects transporter dashboards, client ordering flows, driver execution, admin oversight, and escrow settlement so teams can work from one system instead of juggling disconnected phone calls and paper slips.',
    mission:
      'Digitize transport operations, fleet workflows, and service coordination with practical daily-use tools.',
    vision:
      'Build a reliable operating system for Pakistan’s goods transport ecosystem where seekers, transporters, drivers, and platform administrators share one transparent source of truth.',
  },
  statistics: [
    { key: 'platform', label: 'Unified Platform', value: '1', icon: 'fa-cubes' },
    { key: 'roles', label: 'Role Portals', value: '4', icon: 'fa-users' },
    { key: 'workflow', label: 'Verified Delivery', value: 'OTP', icon: 'fa-check-circle' },
    { key: 'fleet', label: 'Core Modules', value: '5', icon: 'fa-truck' },
  ],
  services: [
    {
      key: 'marketplace',
      title: 'Transport Marketplace',
      description: 'Post structured one-time cargo orders, compare compatible truck bids, and track active trips from one dashboard.',
      icon: 'fa-clipboard-list',
    },
    {
      key: 'fleet',
      title: 'Fleet Operations',
      description: 'Register trucks, configure specifications and routes, dispatch drivers, and review fuel logs in one place.',
      icon: 'fa-truck',
    },
    {
      key: 'payments',
      title: 'Escrow & Wallet Ledger',
      description: 'Track held trip funds, staged settlement releases, security reserves, and transaction history across workflows.',
      icon: 'fa-wallet',
    },
    {
      key: 'analytics',
      title: 'Operational Visibility',
      description: 'Monitor trip progress, dispute arbitration, earnings summaries, and fleet readiness across portals.',
      icon: 'fa-chart-line',
    },
    {
      key: 'security',
      title: 'Secure Access',
      description: 'Protect accounts with role isolation, device session controls, OTP recovery, and MPIN step-up checks.',
      icon: 'fa-shield-alt',
    },
  ],
  team: [
    {
      name: 'Operations Team',
      role: 'Fleet and Jobs',
      bio: 'Shapes the workflows around trucks, driver dispatch, fuel logging, and real operational handoffs.',
      initials: 'OPS',
    },
    {
      name: 'Platform and Security',
      role: 'Access and Reliability',
      bio: 'Keeps authentication, recovery, security settings, and ledger integrity aligned with production standards.',
      initials: 'SEC',
    },
  ],
  timeline: [
    {
      year: 2023,
      title: 'Foundation',
      description: 'The platform direction began around real transport operations and the need to remove fragmented phone-and-slip coordination.',
    },
    {
      year: 2024,
      title: 'Unified Transporter Workflow',
      description: 'Truck management, job bidding, and account operations were shaped into a single transporter experience.',
    },
    {
      year: 2025,
      title: 'Driver & Admin Oversight',
      description: 'Dedicated driver dispatch, OTP delivery verification, and administrative dispute resolution were added.',
    },
    {
      year: 2026,
      title: 'Hardened V1 Portal',
      description: 'Focused one-time transport marketplace with hardened authentication, financial ledger invariants, and responsive React portals.',
    },
  ],
}

export default function About() {
  useEffect(() => {
    document.title = `About ${ABOUT_CONTENT.company.name} - Digi_TransX`
  }, [])

  return (
    <div className="page-about">
      <div className="page-title">
        <h1>About {ABOUT_CONTENT.company.name}</h1>
        <p>{ABOUT_CONTENT.company.tagline}</p>
      </div>

      <div className="stats-section">
        {ABOUT_CONTENT.statistics.map((stat) => (
          <div className="stat-card" key={stat.key}>
            <div className="stat-icon">
              <i className={`fas ${stat.icon}`}></i>
            </div>
            <div className="stat-number">{stat.value}</div>
            <div className="stat-label">{stat.label}</div>
          </div>
        ))}
      </div>

      <div className="about-section">
        <h2 className="section-title">Our Story</h2>
        <p>{ABOUT_CONTENT.company.description}</p>
      </div>

      <div className="mission-vision-section">
        <div className="mv-card">
          <i className="fas fa-bullseye"></i>
          <h3>Our Mission</h3>
          <p>{ABOUT_CONTENT.company.mission}</p>
        </div>
        <div className="mv-card">
          <i className="fas fa-eye"></i>
          <h3>Our Vision</h3>
          <p>{ABOUT_CONTENT.company.vision}</p>
        </div>
      </div>

      <div className="services-section">
        <h2 className="section-title">Our Services</h2>
        <div className="services-grid">
          {ABOUT_CONTENT.services.map((service) => (
            <div className="service-card" key={service.key}>
              <div className="service-icon">
                <i className={`fas ${service.icon}`}></i>
              </div>
              <h3>{service.title}</h3>
              <p>{service.description}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="team-section">
        <h2 className="section-title">Meet Our Team</h2>
        <div className="team-grid">
          {ABOUT_CONTENT.team.map((member) => (
            <div className="team-card" key={member.name}>
              <div className="team-avatar">
                <span>{member.initials}</span>
              </div>
              <h3>{member.name}</h3>
              <p className="team-role">{member.role}</p>
              <p className="team-bio">{member.bio}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="timeline-section">
        <h2 className="section-title">Our Journey</h2>
        <div className="timeline">
          {ABOUT_CONTENT.timeline.map((item) => (
            <div className="timeline-item" key={`${item.year}-${item.title}`}>
              <div className="timeline-dot"></div>
              <div className="timeline-content">
                <div className="timeline-year">{item.year}</div>
                <div className="timeline-title">{item.title}</div>
                <div className="timeline-desc">{item.description}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
