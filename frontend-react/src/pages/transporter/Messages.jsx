import { useSearchParams } from 'react-router-dom'
import ChatWindow from '../../components/chat/ChatWindow'
import '../../styles/pages/transporter-messages.css'

export default function Messages() {
  const [params] = useSearchParams()
  // Contextual deep-link from OrderTracking's "Open Chat". Invalid/inaccessible
  // ids fall back to the first accessible thread inside ChatWindow.
  const raw = params.get('thread')
  const initialThreadId = raw && /^\d+$/.test(raw) ? Number(raw) : null

  return (
    <div className="transporter-messages-page">
      <ChatWindow
        role="transporter"
        heightClass="transporter-messages-height"
        initialThreadId={initialThreadId}
      />
    </div>
  )
}
