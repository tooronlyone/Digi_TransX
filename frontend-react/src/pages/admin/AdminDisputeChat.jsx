import { useParams } from 'react-router-dom'
import ChatWindow from '../../components/chat/ChatWindow'

export default function AdminDisputeChat() {
  const { threadId } = useParams()
  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 26, fontWeight: 800, color: '#0f172a', margin: 0 }}>Dispute Chat</h1>
        <p style={{ color: '#64748b', fontSize: 14, marginTop: 4 }}>Thread #{threadId} — group conversation with client and transporter.</p>
      </div>
      <div style={{ background: '#fff', borderRadius: 14, border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)', overflow: 'hidden' }}>
        <ChatWindow role="admin" initialThreadId={threadId} />
      </div>
    </div>
  )
}
