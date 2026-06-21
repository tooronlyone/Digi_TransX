import ChatWindow from '../../components/chat/ChatWindow'
import { PageTitle } from './clientUtils'

export default function Messages() {
  return (
    <>
      <PageTitle
        title="Messages"
        subtitle="Chat with transporters on each order, including photo/video permission requests."
      />
      <ChatWindow role="client" />
    </>
  )
}
