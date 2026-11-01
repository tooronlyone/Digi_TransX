import { useEffect } from 'react'
import {
  createGenuineActivityHandler,
  installGenuineActivityListeners,
} from '../auth/genuineActivity'

export default function GenuineActivity() {
  useEffect(() => {
    const handler = createGenuineActivityHandler({ documentRef: document })
    return installGenuineActivityListeners(document, handler)
  }, [])

  return null
}
