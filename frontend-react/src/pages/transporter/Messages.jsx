import ChatWindow from '../../components/chat/ChatWindow'

export default function Messages() {
  return (
    <div style={{ margin: '-24px', overflow: 'hidden' }}>
      <ChatWindow role="transporter" heightClass="h-[calc(100vh-70px)]" />
    </div>
  )
}
