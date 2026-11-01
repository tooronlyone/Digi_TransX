import { Link } from 'react-router-dom'
import { FOOTER_LINKS } from './navItems'

export default function TransporterFooter() {
  return (
    <div className="t-footer">
      <p>© 2026 Digi_TransX Transport Services. All rights reserved.</p>
      <div className="t-footer-links">
        {FOOTER_LINKS.map(l => (
          <Link key={l.path} to={l.path}>{l.label}</Link>
        ))}
      </div>
    </div>
  )
}
