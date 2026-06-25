import { Link } from 'react-router-dom'

export default function Leaderboard() {
  return (
      <div className="page-leaderboard">
        <div className="page-title">
          <h1>Leaderboard</h1>
          <p>Top performing transporters on the platform</p>
        </div>
        <div className="leaderboard-placeholder">
          <div className="leaderboard-placeholder-icon">
            <i className="fas fa-trophy"></i>
          </div>
          <h2>Leaderboard coming soon</h2>
          <p>This section will highlight performance, consistency, and reputation across transporters.</p>
          <div className="leaderboard-placeholder-actions">
            <Link to="/transporter/profile" className="action-btn-small">Open Profile</Link>
            <Link to="/transporter/earnings" className="action-btn-small">View Earnings</Link>
          </div>
        </div>
      </div>
    
  )
}
