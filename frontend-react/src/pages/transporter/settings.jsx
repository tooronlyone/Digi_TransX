import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import '../../styles/pages/settings.css'

export default function Settings() {
  const { get, put, post } = useApi()
  const navigate = useNavigate()
  const [section, setSection] = useState('account')
  const [user, setUser] = useState(null)
  const [toast, setToast] = useState({ msg: '', type: 'success' })
  const [saving, setSaving] = useState(false)

  const [account, setAccount] = useState({ companyName: '', email: '', phone: '', address: '', about: '' })
  const [notifs, setNotifs] = useState({ email: true, sms: true, whatsapp: true, push: true, jobAlerts: true, payments: true, system: false, promo: false })
  const [security, setSecurity] = useState({ currentPassword: '', newPassword: '', confirmPassword: '' })
  const [mpinForm, setMpinForm] = useState({ mpin: '', confirmMpin: '' })
  const [otpSent, setOtpSent] = useState(false)
  const [otpCode, setOtpCode] = useState('')
  const [prefs, setPrefs] = useState({ language: 'en', currency: 'PKR', timezone: 'PKT', dateFormat: 'DD/MM/YYYY', theme: 'light', autoRefresh: true, tips: false })
  const [billing, setBilling] = useState({ autoWithdrawal: false, invoiceAuto: true })
  const [advanced, setAdvanced] = useState({ cacheSize: 'medium', dataRetention: '90', analytics: true, debugMode: false, experimental: false })
  const [integrations, setIntegrations] = useState({ mapsEnabled: true, excelExport: true, apiAccess: false })
  const [apiKey, setApiKey] = useState('')
  const [activityLogs, setActivityLogs] = useState([])
  const [savedCard, setSavedCard] = useState(null)
  const [cardForm, setCardForm] = useState({ card_number: '', card_holder: '', card_expiry: '', bank: '' })
  const [showCardForm, setShowCardForm] = useState(false)

  function showToast(msg, type = 'success') {
    setToast({ msg, type })
    setTimeout(() => setToast({ msg: '', type: 'success' }), 3500)
  }

  function normalizeNotifications(raw = {}) {
    return {
      email: raw.email !== false,
      sms: raw.sms !== false,
      whatsapp: raw.whatsapp !== false,
      push: raw.push !== false,
      jobAlerts: raw.jobAlerts !== false,
      payments: raw.payments ?? raw.paymentUpdates ?? true,
      system: raw.system ?? raw.systemUpdates ?? false,
      promo: raw.promo ?? raw.promotions ?? false,
    }
  }

  function normalizePreferences(raw = {}) {
    return {
      language: raw.language || 'en',
      currency: raw.currency || 'PKR',
      timezone: raw.timezone || 'PKT',
      dateFormat: raw.dateFormat || 'DD/MM/YYYY',
      theme: raw.theme || 'light',
      autoRefresh: raw.autoRefresh ?? raw.autoRefreshDashboard ?? true,
      tips: raw.tips ?? raw.showTutorialTips ?? false,
    }
  }

  useEffect(() => {
    Promise.allSettled([get('/api/profile'), get('/api/settings')]).then(([profileRes, settingsRes]) => {
      if (profileRes.status === 'fulfilled' && profileRes.value?.user) {
        const u = profileRes.value.user
        setUser(u)
        setAccount({
          companyName: u.company_name || u.full_name || u.first_name || u.username || '',
          email: u.email || '',
          phone: u.phone || '',
          address: u.address || u.city || '',
          about: u.about || ''
        })
      }
      if (settingsRes.status === 'fulfilled' && settingsRes.value) {
        const s = settingsRes.value.data || settingsRes.value
        if (s.notifications) setNotifs(p => ({ ...p, ...normalizeNotifications(s.notifications) }))
        if (s.preferences) setPrefs(p => ({ ...p, ...normalizePreferences(s.preferences) }))
      }
    }).catch(() => undefined)
    get('/api/wallet/payout-card').then(res => {
      if (res?.success && res.card) setSavedCard(res.card)
    }).catch(() => undefined)
  }, [])

  async function saveCard() {
    setSaving(true)
    try {
      const res = await post('/api/wallet/payout-card', cardForm)
      if (res.success) {
        showToast('Card saved successfully!')
        setShowCardForm(false)
        const cardRes = await get('/api/wallet/payout-card')
        if (cardRes?.success && cardRes.card) setSavedCard(cardRes.card)
      } else {
        showToast(res.message || 'Failed to save card', 'error')
      }
    } catch { showToast('Failed to save card', 'error') }
    finally { setSaving(false) }
  }

  async function saveAccount() {
    setSaving(true)
    try {
      const res = await put('/api/profile', { first_name: account.companyName, phone: account.phone, city: account.address, about: account.about })
      if (res.success && res.user) {
        sessionStorage.setItem('user', JSON.stringify(res.user))
        window.dispatchEvent(new CustomEvent('dtx:user-updated', { detail: res.user }))
      }
      showToast(res.success ? 'Account settings saved!' : res.message || 'Failed', res.success ? 'success' : 'error')
    } catch (e) { showToast('Failed: ' + e.message, 'error') }
    finally { setSaving(false) }
  }

  async function saveNotifications() {
    setSaving(true)
    try {
      const res = await put('/api/settings/notifications', {
        email: notifs.email,
        sms: notifs.sms,
        whatsapp: notifs.whatsapp,
        push: notifs.push,
        jobAlerts: notifs.jobAlerts,
        paymentUpdates: notifs.payments,
        systemUpdates: notifs.system,
        promotions: notifs.promo,
      })
      showToast(res.success ? 'Notification preferences saved!' : 'Failed', res.success ? 'success' : 'error')
    } catch { showToast('Failed to save', 'error') }
    finally { setSaving(false) }
  }

  async function updateSecurity() {
    if (!security.currentPassword) return showToast('Enter your current password', 'error')
    if (!security.newPassword) return showToast('Enter a new password', 'error')
    if (security.newPassword !== security.confirmPassword) return showToast('Passwords do not match', 'error')
    setSaving(true)
    try {
      if (!otpSent) {
        const res = await post('/api/profile/password/request-otp', { current_password: security.currentPassword })
        if (res.success) { setOtpSent(true); showToast('OTP sent to your email!') }
        else showToast(res.message || 'Failed to send OTP', 'error')
      } else {
        if (!otpCode) return showToast('Enter the OTP code', 'error')
        const res = await put('/api/profile/password', { new_password: security.newPassword, otp_code: otpCode })
        if (res.success) {
          showToast('Password changed successfully!')
          setSecurity({ currentPassword: '', newPassword: '', confirmPassword: '' })
          setOtpSent(false); setOtpCode('')
        } else showToast(res.message || 'Failed to update password', 'error')
      }
    } catch { showToast('Request failed', 'error') }
    finally { setSaving(false) }
  }

  async function resendOtp() {
    setSaving(true)
    try { await post('/api/profile/password/request-otp', {}); showToast('OTP resent!') }
    catch { showToast('Failed to resend OTP', 'error') }
    finally { setSaving(false) }
  }

  async function saveMpin() {
    if (!/^\d{4}$/.test(mpinForm.mpin)) return showToast('MPIN must be exactly 4 digits', 'error')
    if (mpinForm.mpin !== mpinForm.confirmMpin) return showToast('MPIN values do not match', 'error')
    setSaving(true)
    try {
      const res = await post('/auth/fast-login/setup', { mpin: mpinForm.mpin })
      if (res.success) {
        setUser(prev => ({ ...(prev || {}), mpin_enabled: true }))
        setMpinForm({ mpin: '', confirmMpin: '' })
        showToast('MPIN enabled successfully!')
      } else showToast(res.message || 'Failed to save MPIN', 'error')
    } catch (e) {
      showToast(e.message || 'Failed to save MPIN', 'error')
    } finally { setSaving(false) }
  }

  async function disableMpin() {
    setSaving(true)
    try {
      const res = await post('/auth/fast-login/disable', {})
      if (res.success) {
        setUser(prev => ({ ...(prev || {}), mpin_enabled: false }))
        setMpinForm({ mpin: '', confirmMpin: '' })
        showToast('MPIN disabled successfully.')
      } else showToast(res.message || 'Failed to disable MPIN', 'error')
    } catch (e) {
      showToast(e.message || 'Failed to disable MPIN', 'error')
    } finally { setSaving(false) }
  }

  async function savePreferences() {
    setSaving(true)
    try {
      const res = await put('/api/settings', {
        language: prefs.language,
        theme: prefs.theme,
        preferred_currency: prefs.currency,
        preferred_timezone: prefs.timezone,
        preferred_date_format: prefs.dateFormat,
        auto_refresh_dashboard: prefs.autoRefresh,
        show_tutorial_tips: prefs.tips,
      })
      showToast(res.success ? 'Preferences saved!' : 'Failed', res.success ? 'success' : 'error')
    } catch { showToast('Failed', 'error') }
    finally { setSaving(false) }
  }

  async function viewLoginActivity() {
    try {
      const res = await get('/api/settings/security/activity')
      if (res.success && res.activity?.length) {
        setActivityLogs(res.activity.slice(0, 5))
        showToast(`Last login: ${res.activity[0]?.created_at || 'N/A'}`)
      } else showToast('No activity found')
    } catch { showToast('Could not load activity', 'error') }
  }

  function generateApiKey() {
    const bytes = new Uint8Array(24); crypto.getRandomValues(bytes)
    setApiKey('dtx_' + Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join(''))
    showToast('New API key generated!')
  }

  async function copyApiKey() {
    if (!apiKey) return showToast('Generate an API key first', 'error')
    try { await navigator.clipboard.writeText(apiKey); showToast('API key copied!') }
    catch { showToast('Copy failed', 'error') }
  }

  const menuItems = [
    { id: 'account',       icon: 'fa-user-cog',   label: 'Account Settings' },
    { id: 'notifications', icon: 'fa-bell',        label: 'Notifications' },
    { id: 'privacy',       icon: 'fa-shield-alt',  label: 'Privacy & Security' },
    { id: 'preferences',   icon: 'fa-sliders-h',   label: 'Preferences' },
    { id: 'billing',       icon: 'fa-credit-card', label: 'Billing & Payments' },
    { id: 'integrations',  icon: 'fa-plug',        label: 'Integrations' },
    { id: 'advanced',      icon: 'fa-tools',       label: 'Advanced' },
  ]

  return (
      <div className="page-settings">
        {toast.msg && (
          <div className={`transporter-settings__toast ${toast.type === 'error' ? 'transporter-settings__toast--error' : 'transporter-settings__toast--success'}`}>
            {toast.msg}
          </div>
        )}

        <div className="transporter-settings__top-bar">
          <div className="transporter-settings__page-title">
            <h1>Settings</h1>
            <p>Manage your account preferences, notifications, and security</p>
          </div>
          <div className="transporter-settings__user-chip">
            <div className="transporter-settings__user-avatar">
              {user ? (user.first_name?.[0] || user.username?.[0] || 'U').toUpperCase() : 'U'}
            </div>
            <div className="transporter-settings__user-details">
              <h3>{user ? ((user.first_name || '') + ' ' + (user.last_name || '')).trim() || user.username : '—'}</h3>
              <p><i className="fas fa-briefcase"></i> {user?.role || 'Transporter'}</p>
            </div>
          </div>
        </div>

        <div className="transporter-settings__container">
          <div className="transporter-settings__sidebar">
            <ul className="transporter-settings__menu">
              {menuItems.map(item => (
                <li key={item.id} className="transporter-settings__menu-item">
                  <a href={`#${item.id}`}
                    className={`transporter-settings__menu-link${section === item.id ? ' transporter-settings__menu-link--active' : ''}`}
                    onClick={e => { e.preventDefault(); setSection(item.id) }}>
                    <i className={`fas ${item.icon}`}></i>{item.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          <div className="transporter-settings__content">

            {section === 'account' && (
              <div className="transporter-settings__section">
                <div className="transporter-settings__section-header">
                  <h3><i className="fas fa-user-cog"></i> Account Settings</h3>
                  <p>Update your account information and profile details</p>
                </div>
                <div className="transporter-settings__form-row">
                  <div className="transporter-settings__form-group">
                    <label className="transporter-settings__label">Full Name / Company</label>
                    <input type="text" className="transporter-settings__input" value={account.companyName}
                      onChange={e => setAccount(p => ({ ...p, companyName: e.target.value }))} placeholder="Enter name" />
                  </div>
                  <div className="transporter-settings__form-group">
                    <label className="transporter-settings__label">Email Address <span className="transporter-settings__label-hint">(read-only)</span></label>
                    <input type="email" className="transporter-settings__input transporter-settings__input--readonly" value={account.email} readOnly />
                  </div>
                </div>
                <div className="transporter-settings__form-row">
                  <div className="transporter-settings__form-group">
                    <label className="transporter-settings__label">Phone Number</label>
                    <input type="tel" className="transporter-settings__input" value={account.phone}
                      onChange={e => setAccount(p => ({ ...p, phone: e.target.value }))} placeholder="+92 300 0000000" />
                  </div>
                  <div className="transporter-settings__form-group">
                    <label className="transporter-settings__label">City / Address</label>
                    <input type="text" className="transporter-settings__input" value={account.address}
                      onChange={e => setAccount(p => ({ ...p, address: e.target.value }))} placeholder="Enter city or address" />
                  </div>
                </div>
                <div className="transporter-settings__form-group">
                  <label className="transporter-settings__label">About Your Business</label>
                  <textarea className="transporter-settings__input" rows="4" value={account.about}
                    onChange={e => setAccount(p => ({ ...p, about: e.target.value }))} placeholder="Describe your business..."></textarea>
                </div>
                <div className="transporter-settings__btn-group">
                  <button type="button" className="transporter-settings__btn transporter-settings__btn--primary" onClick={saveAccount} disabled={saving}>
                    <i className="fas fa-save"></i> {saving ? 'Saving...' : 'Save Changes'}
                  </button>
                  <button type="button" className="transporter-settings__btn transporter-settings__btn--secondary" onClick={() => window.location.reload()}>
                    <i className="fas fa-undo"></i> Reset
                  </button>
                </div>
              </div>
            )}

            {section === 'notifications' && (
              <div className="transporter-settings__section">
                <div className="transporter-settings__section-header">
                  <h3><i className="fas fa-bell"></i> Notification Settings</h3>
                  <p>Control how and when you receive notifications</p>
                </div>
                {[
                  { key: 'email', label: 'Email Notifications', desc: 'Receive notifications via email' },
                  { key: 'sms',   label: 'SMS Notifications',   desc: 'Get important alerts via SMS' },
                  { key: 'whatsapp', label: 'WhatsApp Notifications', desc: 'Receive time-critical dispatch alerts on WhatsApp' },
                  { key: 'push',  label: 'Push Notifications',  desc: 'Receive real-time browser updates' },
                ].map(item => (
                  <div key={item.key} className="transporter-settings__toggle-item">
                    <div className="transporter-settings__toggle-text"><strong>{item.label}</strong><p className="transporter-settings__help-text">{item.desc}</p></div>
                    <label className="transporter-settings__toggle-switch">
                      <input type="checkbox" checked={notifs[item.key]}
                        onChange={e => setNotifs(p => ({ ...p, [item.key]: e.target.checked }))} />
                      <span className="transporter-settings__toggle-slider"></span>
                    </label>
                  </div>
                ))}
                <h4 className="transporter-settings__subsection-title">Notification Types</h4>
                {[
                  { key: 'jobAlerts', label: 'New Job Alerts',    desc: 'Get notified when matching jobs are posted' },
                  { key: 'payments',  label: 'Payment Updates',   desc: 'Notifications for payments and withdrawals' },
                  { key: 'system',    label: 'System Updates',    desc: 'Platform updates and new features' },
                  { key: 'promo',     label: 'Promotional Offers',desc: 'Receive offers and discounts' },
                ].map(item => (
                  <div key={item.key} className="transporter-settings__toggle-item">
                    <div className="transporter-settings__toggle-text"><strong>{item.label}</strong><p className="transporter-settings__help-text">{item.desc}</p></div>
                    <label className="transporter-settings__toggle-switch">
                      <input type="checkbox" checked={notifs[item.key]}
                        onChange={e => setNotifs(p => ({ ...p, [item.key]: e.target.checked }))} />
                      <span className="transporter-settings__toggle-slider"></span>
                    </label>
                  </div>
                ))}
                <div className="transporter-settings__btn-group">
                  <button type="button" className="transporter-settings__btn transporter-settings__btn--primary" onClick={saveNotifications} disabled={saving}>
                    <i className="fas fa-save"></i> {saving ? 'Saving...' : 'Save Preferences'}
                  </button>
                </div>
              </div>
            )}

            {section === 'privacy' && (
              <div className="transporter-settings__section">
                <div className="transporter-settings__section-header">
                  <h3><i className="fas fa-shield-alt"></i> Privacy &amp; Security</h3>
                  <p>Manage your privacy settings and account security</p>
                </div>
                <div className="transporter-settings__form-group">
                  <label className="transporter-settings__label">Current Password</label>
                  <input type="password" className="transporter-settings__input" value={security.currentPassword}
                    onChange={e => setSecurity(p => ({ ...p, currentPassword: e.target.value }))} placeholder="Enter current password" />
                </div>
                <div className="transporter-settings__form-row">
                  <div className="transporter-settings__form-group">
                    <label className="transporter-settings__label">New Password</label>
                    <input type="password" className="transporter-settings__input" value={security.newPassword}
                      onChange={e => setSecurity(p => ({ ...p, newPassword: e.target.value }))} placeholder="Enter new password" />
                  </div>
                  <div className="transporter-settings__form-group">
                    <label className="transporter-settings__label">Confirm Password</label>
                    <input type="password" className="transporter-settings__input" value={security.confirmPassword}
                      onChange={e => setSecurity(p => ({ ...p, confirmPassword: e.target.value }))} placeholder="Confirm new password" />
                  </div>
                </div>
                {otpSent && (
                  <div className="transporter-settings__form-row">
                    <div className="transporter-settings__form-group">
                      <label className="transporter-settings__label">Email OTP</label>
                      <input type="text" className="transporter-settings__input" inputMode="numeric" maxLength="6"
                        value={otpCode} onChange={e => setOtpCode(e.target.value)} placeholder="Enter 6 digit OTP" />
                    </div>
                  </div>
                )}
                <p className="transporter-settings__help-text transporter-settings__help-text--spaced">
                  {otpSent
                    ? 'OTP sent to your email. Enter it above then click Verify & Update.'
                    : 'Enter a new password and click Update Security to receive an OTP on your email.'}
                </p>
                <div className="transporter-settings__mpin-panel">
                  <h4 className="transporter-settings__mpin-title">Fast Login MPIN</h4>
                  <p className="transporter-settings__help-text">
                    Optional 4 digit MPIN for the last logged-in account on this device.
                  </p>
                  <div className="transporter-settings__form-row">
                    <div className="transporter-settings__form-group">
                      <label className="transporter-settings__label">4 Digit MPIN</label>
                      <input
                        type="password"
                        className="transporter-settings__input"
                        inputMode="numeric"
                        maxLength="4"
                        value={mpinForm.mpin}
                        onChange={e => setMpinForm(p => ({ ...p, mpin: e.target.value.replace(/\D/g, '').slice(0, 4) }))}
                        placeholder="Enter 4 digits"
                      />
                    </div>
                    <div className="transporter-settings__form-group">
                      <label className="transporter-settings__label">Confirm MPIN</label>
                      <input
                        type="password"
                        className="transporter-settings__input"
                        inputMode="numeric"
                        maxLength="4"
                        value={mpinForm.confirmMpin}
                        onChange={e => setMpinForm(p => ({ ...p, confirmMpin: e.target.value.replace(/\D/g, '').slice(0, 4) }))}
                        placeholder="Re-enter 4 digits"
                      />
                    </div>
                  </div>
                  <div className="transporter-settings__btn-group">
                    <button type="button" className="transporter-settings__btn transporter-settings__btn--primary" onClick={saveMpin} disabled={saving}>
                      <i className="fas fa-lock"></i> {user?.mpin_enabled ? 'Update MPIN' : 'Enable MPIN'}
                    </button>
                    {user?.mpin_enabled && (
                      <button type="button" className="transporter-settings__btn transporter-settings__btn--secondary" onClick={disableMpin} disabled={saving}>
                        <i className="fas fa-lock-open"></i> Disable MPIN
                      </button>
                    )}
                  </div>
                </div>
                <div className="transporter-settings__cards">
                  <div className="transporter-settings__card"
                    onClick={() => showToast('Data download request submitted. You will receive an email.')}>
                    <div className="transporter-settings__card-icon"><i className="fas fa-download"></i></div>
                    <h4>Download Your Data</h4>
                    <p>Request a copy of all your personal data</p>
                  </div>
                  <div className="transporter-settings__card"
                    onClick={() => { if (window.confirm('Permanently delete your account? This cannot be undone.')) showToast('Account deletion request submitted.', 'error') }}>
                    <div className="transporter-settings__card-icon"><i className="fas fa-trash-alt"></i></div>
                    <h4>Delete Account</h4>
                    <p>Permanently delete your account and all data</p>
                  </div>
                </div>
                {activityLogs.length > 0 && (
                  <div className="transporter-settings__activity-panel">
                    <h4 className="transporter-settings__activity-title">Recent Login Activity</h4>
                    {activityLogs.map((log, i) => (
                      <div key={i} className="transporter-settings__activity-entry">
                        <i className="fas fa-circle"></i>
                        {log.created_at} &mdash; {log.ip_address || 'Unknown IP'}
                      </div>
                    ))}
                  </div>
                )}
                <div className="transporter-settings__btn-group">
                  <button type="button" className="transporter-settings__btn transporter-settings__btn--primary" onClick={updateSecurity} disabled={saving}>
                    <i className="fas fa-save"></i> {saving ? 'Processing...' : (otpSent ? 'Verify & Update' : 'Update Security')}
                  </button>
                  {otpSent && (
                    <button type="button" className="transporter-settings__btn transporter-settings__btn--secondary" onClick={resendOtp} disabled={saving}>
                      <i className="fas fa-paper-plane"></i> Resend OTP
                    </button>
                  )}
                  <button type="button" className="transporter-settings__btn transporter-settings__btn--secondary" onClick={viewLoginActivity}>
                    <i className="fas fa-history"></i> View Login Activity
                  </button>
                </div>
              </div>
            )}

            {section === 'preferences' && (
              <div className="transporter-settings__section">
                <div className="transporter-settings__section-header">
                  <h3><i className="fas fa-sliders-h"></i> Preferences</h3>
                  <p>Customize your Digi_TransX experience</p>
                </div>
                {[
                  { id: 'language', label: 'Language', options: [{ val: 'en', label: 'English' }, { val: 'ur', label: 'Urdu' }, { val: 'hi', label: 'Hindi' }] },
                  { id: 'currency', label: 'Currency', options: [{ val: 'PKR', label: 'Pakistani Rupee (PKR)' }, { val: 'CNY', label: 'Chinese Yuan (CNY)' }] },
                  { id: 'timezone', label: 'Timezone', options: [{ val: 'PKT', label: 'Pakistani Standard Time (PKT)' }, { val: 'UTC', label: 'UTC' }, { val: 'EST', label: 'Eastern Standard Time' }] },
                ].map(field => (
                  <div key={field.id} className="transporter-settings__form-group">
                    <label className="transporter-settings__label">{field.label}</label>
                    <div className="transporter-settings__select-wrapper">
                      <select className="transporter-settings__input" value={prefs[field.id]}
                        onChange={e => setPrefs(p => ({ ...p, [field.id]: e.target.value }))}>
                        {field.options.map(o => <option key={o.val} value={o.val}>{o.label}</option>)}
                      </select>
                      <i className="fas fa-chevron-down"></i>
                    </div>
                  </div>
                ))}
                <div className="transporter-settings__form-group">
                  <label className="transporter-settings__label">Date Format</label>
                  <div className="transporter-settings__radio-group">
                    {[{ val: 'DD/MM/YYYY' }, { val: 'MM/DD/YYYY' }, { val: 'YYYY-MM-DD' }].map(f => (
                      <div key={f.val} className="transporter-settings__radio-item">
                        <input type="radio" id={`df-${f.val}`} name="dateFormat" value={f.val}
                          checked={prefs.dateFormat === f.val} onChange={e => setPrefs(p => ({ ...p, dateFormat: e.target.value }))} />
                        <label htmlFor={`df-${f.val}`}>{f.val}</label>
                      </div>
                    ))}
                  </div>
                </div>
                {[
                  { key: 'autoRefresh', label: 'Auto-refresh Dashboard', desc: 'Automatically refresh dashboard data every 5 minutes' },
                  { key: 'tips',        label: 'Show Tutorial Tips',      desc: 'Display helpful tips for new features' },
                ].map(item => (
                  <div key={item.key} className="transporter-settings__toggle-item">
                    <div className="transporter-settings__toggle-text"><strong>{item.label}</strong><p className="transporter-settings__help-text">{item.desc}</p></div>
                    <label className="transporter-settings__toggle-switch">
                      <input type="checkbox" checked={prefs[item.key]}
                        onChange={e => setPrefs(p => ({ ...p, [item.key]: e.target.checked }))} />
                      <span className="transporter-settings__toggle-slider"></span>
                    </label>
                  </div>
                ))}
                <div className="transporter-settings__btn-group">
                  <button type="button" className="transporter-settings__btn transporter-settings__btn--primary" onClick={savePreferences} disabled={saving}>
                    <i className="fas fa-save"></i> {saving ? 'Saving...' : 'Save Preferences'}
                  </button>
                  <button type="button" className="transporter-settings__btn transporter-settings__btn--secondary"
                    onClick={() => setPrefs({ language: 'en', currency: 'PKR', timezone: 'PKT', dateFormat: 'DD/MM/YYYY', theme: 'light', autoRefresh: true, tips: false })}>
                    <i className="fas fa-undo"></i> Reset to Defaults
                  </button>
                </div>
              </div>
            )}

            {section === 'billing' && (
              <div className="transporter-settings__section">
                <div className="transporter-settings__section-header">
                  <h3><i className="fas fa-credit-card"></i> Billing &amp; Payments</h3>
                  <p>Manage your payment methods and billing information</p>
                </div>

                {savedCard && !showCardForm && (
                  <div className="transporter-settings__bank-card">
                    <div className="transporter-settings__bank-card-top">
                      <i className="fas fa-credit-card"></i>
                      <span>{savedCard.bank || 'Bank Card'}</span>
                    </div>
                    <div className="transporter-settings__bank-card-number">{savedCard.card_number_masked}</div>
                    <div className="transporter-settings__bank-card-bottom">
                      <div><span>Card Holder</span>{savedCard.card_holder}</div>
                      <div><span>Expiry</span>{savedCard.card_expiry}</div>
                    </div>
                  </div>
                )}

                {!showCardForm && (
                  <div className="transporter-settings__btn-group">
                    <button type="button" className="transporter-settings__btn transporter-settings__btn--primary" onClick={() => { setShowCardForm(true); setCardForm({ card_number: '', card_holder: '', card_expiry: '', bank: '' }) }}>
                      <i className={`fas ${savedCard ? 'fa-edit' : 'fa-plus-circle'}`}></i> {savedCard ? 'Update Card' : 'Add Payment Method'}
                    </button>
                  </div>
                )}

                {showCardForm && (
                  <div className="transporter-settings__card-form">
                    <h4 className="transporter-settings__subsection-title">{savedCard ? 'Update Card' : 'Add Payment Method'}</h4>
                    <div className="transporter-settings__form-group">
                      <label className="transporter-settings__label">Card Number</label>
                      <input type="text" className="transporter-settings__input" placeholder="1234 5678 9012 3456" maxLength="19"
                        value={cardForm.card_number}
                        onChange={e => {
                          const v = e.target.value.replace(/[^\d]/g, '').replace(/(.{4})/g, '$1 ').trim()
                          setCardForm(p => ({ ...p, card_number: v }))
                        }} />
                    </div>
                    <div className="transporter-settings__form-group">
                      <label className="transporter-settings__label">Card Holder Name</label>
                      <input type="text" className="transporter-settings__input" placeholder="Name as on card"
                        value={cardForm.card_holder}
                        onChange={e => setCardForm(p => ({ ...p, card_holder: e.target.value }))} />
                    </div>
                    <div className="transporter-settings__form-row">
                      <div className="transporter-settings__form-group">
                        <label className="transporter-settings__label">Expiry (MM/YY)</label>
                        <input type="text" className="transporter-settings__input" placeholder="MM/YY" maxLength="5"
                          value={cardForm.card_expiry}
                          onChange={e => {
                            let v = e.target.value.replace(/[^\d]/g, '')
                            if (v.length >= 2) v = v.slice(0, 2) + '/' + v.slice(2, 4)
                            setCardForm(p => ({ ...p, card_expiry: v }))
                          }} />
                      </div>
                      <div className="transporter-settings__form-group">
                        <label className="transporter-settings__label">Bank Name <span className="transporter-settings__label-hint">(optional)</span></label>
                        <input type="text" className="transporter-settings__input" placeholder="e.g. HBL, UBL, Meezan"
                          value={cardForm.bank}
                          onChange={e => setCardForm(p => ({ ...p, bank: e.target.value }))} />
                      </div>
                    </div>
                    <div className="transporter-settings__btn-group">
                      <button type="button" className="transporter-settings__btn transporter-settings__btn--primary" onClick={saveCard} disabled={saving}>
                        <i className="fas fa-save"></i> {saving ? 'Saving...' : 'Save Card'}
                      </button>
                      <button type="button" className="transporter-settings__btn transporter-settings__btn--secondary" onClick={() => setShowCardForm(false)}>
                        <i className="fas fa-times"></i> Cancel
                      </button>
                    </div>
                  </div>
                )}

                <h4 className="transporter-settings__subsection-title transporter-settings__subsection-title--spaced">Payment Settings</h4>
                {[
                  { key: 'autoWithdrawal', label: 'Auto-Withdrawal',       desc: 'Auto-transfer earnings to your bank every week' },
                  { key: 'invoiceAuto',    label: 'Invoice Auto-generation',desc: 'Auto-generate invoices for completed jobs' },
                ].map(item => (
                  <div key={item.key} className="transporter-settings__toggle-item">
                    <div className="transporter-settings__toggle-text"><strong>{item.label}</strong><p className="transporter-settings__help-text">{item.desc}</p></div>
                    <label className="transporter-settings__toggle-switch">
                      <input type="checkbox" checked={billing[item.key]}
                        onChange={e => setBilling(p => ({ ...p, [item.key]: e.target.checked }))} />
                      <span className="transporter-settings__toggle-slider"></span>
                    </label>
                  </div>
                ))}
                <div className="transporter-settings__btn-group">
                  <button type="button" className="transporter-settings__btn transporter-settings__btn--primary" onClick={() => navigate('/transporter/account-history')}>
                    <i className="fas fa-history"></i> Payment History
                  </button>
                </div>
              </div>
            )}

            {section === 'integrations' && (
              <div className="transporter-settings__section">
                <div className="transporter-settings__section-header">
                  <h3><i className="fas fa-plug"></i> Integrations</h3>
                  <p>Connect Digi_TransX with other tools and services</p>
                </div>
                <div className="transporter-settings__cards">
                  <div className="transporter-settings__card">
                    <div className="transporter-settings__card-icon" style={{ background: 'linear-gradient(135deg, #4285F4, #34A853)' }}><i className="fas fa-map-marker-alt"></i></div>
                    <h4>Google Maps</h4>
                    <p>Route planning and real-time tracking</p>
                    <div className="transporter-settings__integration-action">
                      <label className="transporter-settings__toggle-switch">
                        <input type="checkbox" checked={integrations.mapsEnabled}
                          onChange={e => setIntegrations(p => ({ ...p, mapsEnabled: e.target.checked }))} />
                        <span className="transporter-settings__toggle-slider"></span>
                      </label>
                      <span className="transporter-settings__integration-status">{integrations.mapsEnabled ? 'Connected' : 'Disabled'}</span>
                    </div>
                  </div>
                  <div className="transporter-settings__card">
                    <div className="transporter-settings__card-icon" style={{ background: 'linear-gradient(135deg, #FF6B6B, #FF8E53)' }}><i className="fas fa-file-excel"></i></div>
                    <h4>Export to Excel</h4>
                    <p>Export job history, earnings, and reports</p>
                    <div className="transporter-settings__integration-action">
                      <label className="transporter-settings__toggle-switch">
                        <input type="checkbox" checked={integrations.excelExport}
                          onChange={e => setIntegrations(p => ({ ...p, excelExport: e.target.checked }))} />
                        <span className="transporter-settings__toggle-slider"></span>
                      </label>
                      <span className="transporter-settings__integration-status">{integrations.excelExport ? 'Enabled' : 'Disabled'}</span>
                    </div>
                  </div>
                  <div className="transporter-settings__card">
                    <div className="transporter-settings__card-icon" style={{ background: 'linear-gradient(135deg, #6A11CB, #2575FC)' }}><i className="fas fa-cloud"></i></div>
                    <h4>Cloud Storage</h4>
                    <p>Backup documents to Google Drive or Dropbox</p>
                    <div className="transporter-settings__integration-action">
                      <button type="button" className="transporter-settings__btn transporter-settings__btn--secondary transporter-settings__btn--sm"
                        onClick={() => showToast('Cloud storage integration coming soon!')}>
                        <i className="fas fa-link"></i> Connect
                      </button>
                    </div>
                  </div>
                </div>
                <h4 className="transporter-settings__subsection-title transporter-settings__subsection-title--spaced">API Access</h4>
                <div className="transporter-settings__form-group">
                  <label className="transporter-settings__label">API Key</label>
                  <div className="transporter-settings__api-row">
                    <input type="text" className="transporter-settings__input transporter-settings__input--mono" value={apiKey} readOnly
                      placeholder="Click Generate New API Key" />
                    <button type="button" className="transporter-settings__btn transporter-settings__btn--secondary transporter-settings__btn--icon" onClick={copyApiKey} title="Copy API Key">
                      <i className="fas fa-copy"></i>
                    </button>
                  </div>
                </div>
                <div className="transporter-settings__toggle-item">
                  <div className="transporter-settings__toggle-text"><strong>Enable API Access</strong><p className="transporter-settings__help-text">Allow external systems to access your data via API</p></div>
                  <label className="transporter-settings__toggle-switch">
                    <input type="checkbox" checked={integrations.apiAccess}
                      onChange={e => setIntegrations(p => ({ ...p, apiAccess: e.target.checked }))} />
                    <span className="transporter-settings__toggle-slider"></span>
                  </label>
                </div>
                <div className="transporter-settings__btn-group">
                  <button type="button" className="transporter-settings__btn transporter-settings__btn--primary" onClick={generateApiKey}>
                    <i className="fas fa-key"></i> Generate New API Key
                  </button>
                  <button type="button" className="transporter-settings__btn transporter-settings__btn--secondary" onClick={() => showToast('API documentation coming soon!')}>
                    <i className="fas fa-book"></i> API Documentation
                  </button>
                </div>
              </div>
            )}

            {section === 'advanced' && (
              <div className="transporter-settings__section">
                <div className="transporter-settings__section-header">
                  <h3><i className="fas fa-tools"></i> Advanced Settings</h3>
                  <p>Advanced configuration options for power users</p>
                </div>
                {[
                  { id: 'cacheSize', label: 'Cache Size', options: [{ val: 'small', label: 'Small (50 MB)' }, { val: 'medium', label: 'Medium (100 MB)' }, { val: 'large', label: 'Large (250 MB)' }, { val: 'unlimited', label: 'Unlimited' }] },
                  { id: 'dataRetention', label: 'Data Retention Period', options: [{ val: '30', label: '30 days' }, { val: '90', label: '90 days' }, { val: '180', label: '180 days' }, { val: '365', label: '1 year' }, { val: 'forever', label: 'Forever' }] },
                ].map(field => (
                  <div key={field.id} className="transporter-settings__form-group">
                    <label className="transporter-settings__label">{field.label}</label>
                    <div className="transporter-settings__select-wrapper">
                      <select className="transporter-settings__input" value={advanced[field.id]}
                        onChange={e => setAdvanced(p => ({ ...p, [field.id]: e.target.value }))}>
                        {field.options.map(o => <option key={o.val} value={o.val}>{o.label}</option>)}
                      </select>
                      <i className="fas fa-chevron-down"></i>
                    </div>
                  </div>
                ))}
                {[
                  { key: 'analytics',    label: 'Analytics & Tracking',  desc: 'Allow anonymous usage data collection' },
                  { key: 'debugMode',    label: 'Debug Mode',            desc: 'Enable detailed logging for troubleshooting' },
                  { key: 'experimental', label: 'Experimental Features', desc: 'Try new features before official release' },
                ].map(item => (
                  <div key={item.key} className="transporter-settings__toggle-item">
                    <div className="transporter-settings__toggle-text"><strong>{item.label}</strong><p className="transporter-settings__help-text">{item.desc}</p></div>
                    <label className="transporter-settings__toggle-switch">
                      <input type="checkbox" checked={advanced[item.key]}
                        onChange={e => setAdvanced(p => ({ ...p, [item.key]: e.target.checked }))} />
                      <span className="transporter-settings__toggle-slider"></span>
                    </label>
                  </div>
                ))}
                <h4 className="transporter-settings__subsection-title transporter-settings__subsection-title--spaced">System Actions</h4>
                <div className="transporter-settings__btn-group">
                  <button type="button" className="transporter-settings__btn transporter-settings__btn--secondary"
                    onClick={() => { try { localStorage.clear() } catch { /* ignore unavailable storage */ } showToast('Cache cleared!') }}>
                    <i className="fas fa-broom"></i> Clear Cache
                  </button>
                  <button type="button" className="transporter-settings__btn transporter-settings__btn--secondary" onClick={() => window.location.reload()}>
                    <i className="fas fa-sync-alt"></i> Refresh All Data
                  </button>
                  <button type="button" className="transporter-settings__btn transporter-settings__btn--danger"
                    onClick={() => {
                      if (window.confirm('Reset all settings to default? This cannot be undone.')) {
                        setPrefs({ language: 'en', currency: 'PKR', timezone: 'PKT', dateFormat: 'DD/MM/YYYY', theme: 'light', autoRefresh: true, tips: false })
                        setNotifs({ email: true, sms: true, whatsapp: true, push: true, jobAlerts: true, payments: true, system: false, promo: false })
                        showToast('All settings reset to defaults!')
                      }
                    }}>
                    <i className="fas fa-redo"></i> Reset All Settings
                  </button>
                </div>
              </div>
            )}

          </div>
        </div>


        {/* ========================================
            INTERNAL STYLES — Settings Page
            ========================================
            COMPONENT: Settings
            FILE: pages/transporter/settings.jsx
            LAYOUT: Rendered inside TransporterLayout's .main-content
                    (navbar 70px + sidebar 70px already handled by layout)
            NAMING: BEM — .transporter-settings__[element]--[modifier]
            RESPONSIVE: 5 breakpoints — 576px, 768px, 992px, 1920px, 2560px
            ======================================== */}
        
      </div>
  )
}
