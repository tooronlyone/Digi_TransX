import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

const ABOUT_FALLBACK = {
  company: {
    name: 'Digi_TransX',
    tagline: "Pakistan's smart transport platform for jobs, fleet control, payments, analytics, and guided support.",
    description:
      'Digi_TransX brings transport operations into one practical workspace. The current software connects transporter dashboards, client ordering flows, admin oversight, payments, analytics, and assistant guidance so teams can work from one system instead of juggling disconnected tools.',
    mission:
      'Digitize transport operations, fleet workflows, and service coordination with practical daily-use tools.',
    vision:
      'Build a reliable operating system for the transport ecosystem where transporters, clients, admins, and assistant workflows share the same source of truth.',
  },
  statistics: [
    { key: 'platform', label: 'Unified Platform', value: '1', icon: 'fa-cubes' },
    { key: 'roles', label: 'Role Portals', value: '3', icon: 'fa-users' },
    { key: 'services', label: 'Service Lines', value: '3', icon: 'fa-layer-group' },
    { key: 'fleet', label: 'Fleet Modules', value: '5', icon: 'fa-truck' },
  ],
  services: [
    {
      key: 'marketplace',
      title: 'Transport Marketplace',
      description: 'Browse work, manage active jobs, and keep shipment workflows moving from one dashboard.',
      icon: 'fa-clipboard-list',
    },
    {
      key: 'fleet',
      title: 'Fleet Operations',
      description: 'Add trucks, update configurations, review service history, and manage readiness in one place.',
      icon: 'fa-truck',
    },
    {
      key: 'payments',
      title: 'Payments and Earnings',
      description: 'Process payments, review payout activity, and track financial movement across transporter workflows.',
      icon: 'fa-wallet',
    },
    {
      key: 'analytics',
      title: 'Analytics and Insights',
      description: 'Use dashboards, analytics pages, and predictive surfaces to monitor operational performance.',
      icon: 'fa-chart-line',
    },
    {
      key: 'security',
      title: 'Secure Access',
      description: 'Support safe login, unlock flows, password recovery, and guarded access across the platform.',
      icon: 'fa-shield-alt',
    },
    {
      key: 'assistant',
      title: 'AI Assistant',
      description: 'Guide users through pages, explain workflows, and reduce confusion during real operational tasks.',
      icon: 'fa-robot',
    },
  ],
  team: [
    {
      name: 'Operations Team',
      role: 'Fleet and Jobs',
      bio: 'Shapes the workflows around trucks, assignments, maintenance follow-up, and real operational handoffs.',
      initials: 'OPS',
    },
    {
      name: 'Platform and Security',
      role: 'Access and Reliability',
      bio: 'Keeps authentication, recovery, security settings, and operational reliability aligned with production needs.',
      initials: 'SEC',
    },
    {
      name: 'AI Enablement',
      role: 'Guided Workflows',
      bio: 'Builds assistant experiences that explain product flows clearly and help users take the next practical step.',
      initials: 'AI',
    },
  ],
  timeline: [
    {
      year: 2023,
      title: 'Foundation',
      description: 'The platform direction began around the need to digitize transport work without adding operational friction.',
    },
    {
      year: 2024,
      title: 'Unified Transporter Workflow',
      description: 'Truck management, job handling, and account operations were shaped into a single transporter experience.',
    },
    {
      year: 2025,
      title: 'Admin and Assistant Expansion',
      description: 'Administrative visibility and assistant-guided support were expanded to cover more of the product flow.',
    },
    {
      year: 2026,
      title: 'Modern Portal Experience',
      description: 'The current product reflects a cleaner React portal with structured About, Help, Contact, and workflow endpoints.',
    },
  ],
}

async function requestJson(path) {
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(`Request failed: ${path}`)
  }
  return response.json()
}

function normalizeCompany(company) {
  return {
    ...ABOUT_FALLBACK.company,
    ...(company && typeof company === 'object' ? company : {}),
  }
}

function normalizeStatistics(statistics) {
  if (Array.isArray(statistics) && statistics.length > 0) {
    return statistics.map((stat, index) => ({
      key: stat.key || `stat-${index}`,
      label: stat.label || ABOUT_FALLBACK.statistics[index]?.label || 'Metric',
      value: String(stat.value ?? ABOUT_FALLBACK.statistics[index]?.value ?? '-'),
      icon: stat.icon || ABOUT_FALLBACK.statistics[index]?.icon || 'fa-chart-bar',
    }))
  }

  if (statistics && typeof statistics === 'object') {
    return [
      {
        key: 'platform',
        label: 'Unified Platform',
        value: String(statistics.platforms ?? 1),
        icon: 'fa-cubes',
      },
      {
        key: 'services',
        label: 'Service Lines',
        value: String(statistics.service_lines ?? 3),
        icon: 'fa-layer-group',
      },
      {
        key: 'fleet',
        label: 'Fleet Modules',
        value: String(statistics.fleet_modules ?? 5),
        icon: 'fa-truck',
      },
      {
        key: 'roles',
        label: 'Role Portals',
        value: '3',
        icon: 'fa-users',
      },
    ]
  }

  return ABOUT_FALLBACK.statistics
}

function normalizeServices(services) {
  if (!Array.isArray(services) || services.length === 0) {
    return ABOUT_FALLBACK.services
  }

  const fallbackByKey = Object.fromEntries(ABOUT_FALLBACK.services.map((service) => [service.key, service]))

  return services.map((service, index) => {
    const fallback = fallbackByKey[service.key] || ABOUT_FALLBACK.services[index] || {}
    return {
      key: service.key || fallback.key || `service-${index}`,
      title: service.title || service.label || fallback.title || 'Platform Service',
      description: service.description || fallback.description || 'Operational service details will be available soon.',
      icon: service.icon || fallback.icon || 'fa-box',
    }
  })
}

function normalizeTeam(team) {
  if (!Array.isArray(team) || team.length === 0) {
    return ABOUT_FALLBACK.team
  }

  const fallbackByName = Object.fromEntries(ABOUT_FALLBACK.team.map((member) => [member.name, member]))

  return team.map((member, index) => {
    const fallback = fallbackByName[member.name] || ABOUT_FALLBACK.team[index] || {}
    return {
      name: member.name || fallback.name || 'Digi_TransX Team',
      role: member.role || member.position || fallback.role || member.focus || 'Platform Team',
      bio: member.bio || fallback.bio || member.focus || 'Platform ownership details will be available soon.',
      initials: member.initials || fallback.initials || 'DT',
    }
  })
}

function normalizeTimeline(timeline) {
  if (!Array.isArray(timeline) || timeline.length === 0) {
    return ABOUT_FALLBACK.timeline
  }

  const fallbackByYear = Object.fromEntries(ABOUT_FALLBACK.timeline.map((item) => [String(item.year), item]))

  return timeline.map((item, index) => {
    const fallback = fallbackByYear[String(item.year)] || ABOUT_FALLBACK.timeline[index] || {}
    return {
      year: item.year || fallback.year || '',
      title: item.title || fallback.title || item.event || 'Milestone',
      description: item.description || fallback.description || item.event || 'Timeline detail will be available soon.',
    }
  })
}

export default function About() {
  const [aboutData, setAboutData] = useState(ABOUT_FALLBACK)

  useEffect(() => {
    let ignore = false

    async function loadAboutData() {
      const [companyResult, teamResult, servicesResult, statisticsResult, timelineResult] = await Promise.allSettled([
        requestJson('/api/about'),
        requestJson('/api/about/team'),
        requestJson('/api/about/services'),
        requestJson('/api/about/statistics'),
        requestJson('/api/about/timeline'),
      ])

      if (ignore) {
        return
      }

      setAboutData({
        company: normalizeCompany(companyResult.status === 'fulfilled' ? companyResult.value?.company : null),
        team: normalizeTeam(teamResult.status === 'fulfilled' ? teamResult.value?.team : null),
        services: normalizeServices(servicesResult.status === 'fulfilled' ? servicesResult.value?.services : null),
        statistics: normalizeStatistics(statisticsResult.status === 'fulfilled' ? statisticsResult.value?.statistics : null),
        timeline: normalizeTimeline(timelineResult.status === 'fulfilled' ? timelineResult.value?.timeline : null),
      })
    }

    loadAboutData().catch(() => {})

    return () => {
      ignore = true
    }
  }, [])

  useEffect(() => {
    document.title = `About ${aboutData.company.name} - Digi_TransX`
  }, [aboutData.company.name])

  return (
      <div className="page-about">
        <div className="page-title">
          <h1>About {aboutData.company.name}</h1>
          <p>{aboutData.company.tagline}</p>
        </div>

        <div className="stats-section">
          {aboutData.statistics.map((stat) => (
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
          <p>{aboutData.company.description}</p>
        </div>

        <div className="mission-vision-section">
          <div className="mv-card">
            <i className="fas fa-bullseye"></i>
            <h3>Our Mission</h3>
            <p>{aboutData.company.mission}</p>
          </div>
          <div className="mv-card">
            <i className="fas fa-eye"></i>
            <h3>Our Vision</h3>
            <p>{aboutData.company.vision}</p>
          </div>
        </div>

        <div className="services-section">
          <h2 className="section-title">Our Services</h2>
          <div className="services-grid">
            {aboutData.services.map((service) => (
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
            {aboutData.team.map((member) => (
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
            {aboutData.timeline.map((item) => (
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
