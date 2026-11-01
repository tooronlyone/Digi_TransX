import { useSearchParams } from 'react-router-dom'
import ChatWindow from '../../components/chat/ChatWindow'
import { PageTitle } from './clientUtils'

export default function Messages() {
  const [params] = useSearchParams()
  // Contextual deep-link from an order's "Open Chat". A non-numeric/inaccessible
  // id is ignored by ChatWindow, which then falls back to the first thread the
  // server allows this user to see.
  const raw = params.get('thread')
  const initialThreadId = raw && /^\d+$/.test(raw) ? Number(raw) : null

  return (
    <>
      <PageTitle
        title="Messages"
        subtitle="Chat with transporters on each order, including photo/video permission requests."
      />
      <ChatWindow role="client" initialThreadId={initialThreadId} />
    </>
  )
}
