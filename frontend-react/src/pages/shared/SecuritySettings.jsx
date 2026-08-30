import LogoutAllAction from '../../components/security/LogoutAllAction'
import MpinManagement from '../../components/security/MpinManagement'
import SessionDeviceManagement from '../../components/security/SessionDeviceManagement'

export default function SecuritySettings() {
  return (
    <main className="security-settings-page">
      <header className="security-settings-page__header">
        <p>Account protection</p>
        <h1>Security settings</h1>
        <span>Manage software-unlock access for this trusted signed-in device.</span>
      </header>
      <div className="security-settings-page__content">
        <MpinManagement />
        <SessionDeviceManagement />
        <LogoutAllAction />
      </div>
    </main>
  )
}
