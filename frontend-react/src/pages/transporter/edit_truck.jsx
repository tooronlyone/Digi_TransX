import { useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

export default function EditTruck() {
  const navigate = useNavigate()
  const { id } = useParams()

  useEffect(() => {
    if (id) navigate(`/transporter/trucks/config/${id}`, { replace: true })
    else navigate('/transporter/trucks', { replace: true })
  }, [id, navigate])

  return (
    <div className="page-edit-truck-redirect">
      <div className="edit-truck-container">
        <div className="loading-state" aria-live="polite">
          <i className="fas fa-spinner" aria-hidden="true"></i>
          <p>Redirecting to truck configuration...</p>
        </div>
      </div>
    </div>
  )
}
