import ChatWindow from '../../components/chat/ChatWindow'
import '../../styles/pages/transporter-messages.css'

export default function Messages() {
  return (
    <div className="transporter-messages-page">
      <ChatWindow role="transporter" heightClass="transporter-messages-height" />
    </div>
  )
}
