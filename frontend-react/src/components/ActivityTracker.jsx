/**
 * Phase 1A containment wrapper. It retains only authenticated router page
 * visits and never patches browser APIs or observes clicks, forms, or fetches.
 */
import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { sendPageVisit } from '../hooks/useTracker'

export default function ActivityTracker({ children }) {
  const location = useLocation()

  useEffect(() => {
    void sendPageVisit(location.pathname)
  }, [location.pathname])

  return children
}
