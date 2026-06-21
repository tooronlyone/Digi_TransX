import TransporterLayout from '../../components/transporter/TransporterLayout'
import WalletWorkspace from '../../components/wallet/WalletWorkspace'

export default function TransporterWallet() {
  return (
    <TransporterLayout>
      <WalletWorkspace portal="transporter" />
    </TransporterLayout>
  )
}
