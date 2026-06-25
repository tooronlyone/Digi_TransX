import { useParams } from 'react-router-dom'
import ChatWindow from '../../components/chat/ChatWindow'

export default function AdminDisputeChat() {
  const { threadId } = useParams()
  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-slate-800 bg-slate-900 p-5">
        <h1 className="text-2xl font-bold text-white">Dispute Chat</h1>
        <p className="mt-2 text-sm text-slate-400">Thread #{threadId}</p>
      </section>
      <div className="text-slate-900">
        <ChatWindow role="admin" initialThreadId={threadId} />
      </div>
    </div>
  )
}
