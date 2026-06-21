import ChatWindow from '../../components/chat/ChatWindow'
import TransporterLayout from '../../components/transporter/TransporterLayout'

export default function Messages() {
  return (
    <TransporterLayout>
      <div className="space-y-6">
        <div className="rounded-2xl bg-white p-6 shadow-sm">
          <h1 className="text-2xl font-bold text-slate-900">Messages</h1>
          <p className="mt-2 text-sm text-slate-500">Stay connected with clients for every order and handle media permissions safely.</p>
        </div>
        <ChatWindow role="transporter" />
      </div>
    </TransporterLayout>
  )
}
