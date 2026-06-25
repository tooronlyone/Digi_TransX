import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'

export default function Settings() {
  const { get, put, post } = useApi()
  const navigate = useNavigate()
  const [section, setSection] = useState('account')
  const [user, setUser] = useState(null)
  const [toast, setToast] = useState({ msg: '', type: 'success' })
  const [saving, setSaving] = useState(false)

  const [account, setAccount] = useState({ companyName: '', email: '', phone: '', address: '', about: '' })
  const [notifs, setNotifs] = useState({ email: true, sms: true, whatsapp: true, push: true, jobAlerts: true, payments: true, system: false, promo: false })
  const [security, setSecurity] = useState({ newPassword: '', confirmPassword: '' })
  const [mpinForm, setMpinForm] = useState({ mpin: '', confirmMpin: '' })
  const [otpSent, setOtpSent] = useState(false)
  const [otpCode, setOtpCode] = useState('')
  const [prefs, setPrefs] = useState({ language: 'en', currency: 'PKR', timezone: 'PKT', dateFormat: 'DD/MM/YYYY', theme: 'light', autoRefresh: true, tips: false })
  const [billing, setBilling] = useState({ autoWithdrawal: false, invoiceAuto: true })
  const [advanced, setAdvanced] = useState({ cacheSize: 'medium', dataRetention: '90', analytics: true, debugMode: false, experimental: false })
  const [integrations, setIntegrations] = useState({ mapsEnabled: true, excelExport: true, apiAccess: false })
  const [apiKey, setApiKey] = useState('')
  const [activityLogs, setActivityLogs] = useState([])

  function showToast(msg, type = 'success') {
    setToast({ msg, type })
    setTimeout(() => setToast({ msg: '', type: 'success' }), 3500)
  }

  function normalizeNotifications(raw = {}) {
    return {
      email: Boolean(raw.email),
      sms: Boolean(raw.sms),
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
          companyName: u.company_name || u.first_name || u.username || '',
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
  }, [])

  async function saveAccount() {
    setSaving(true)
    try {
      const res = await put('/api/profile', { first_name: account.companyName, phone: account.phone, city: account.address, about: account.about })
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
    if (!security.newPassword) return showToast('Enter a new password', 'error')
    if (security.newPassword !== security.confirmPassword) return showToast('Passwords do not match', 'error')
    setSaving(true)
    try {
      if (!otpSent) {
        const res = await post('/api/profile/password/request-otp', {})
        if (res.success) { setOtpSent(true); showToast('OTP sent to your email!') }
        else showToast(res.message || 'Failed to send OTP', 'error')
      } else {
        if (!otpCode) return showToast('Enter the OTP code', 'error')
        const res = await put('/api/profile/password', { new_password: security.newPassword, otp_code: otpCode })
        if (res.success) {
          showToast('Password changed successfully!')
          setSecurity({ newPassword: '', confirmPassword: '' })
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
          <div style={{
            position: 'fixed', top: '1rem', right: '1rem', zIndex: 9999,
            background: toast.type === 'error' ? '#fee2e2' : '#dcfce7',
            color: toast.type === 'error' ? '#dc2626' : '#16a34a',
            padding: '0.75rem 1.25rem', borderRadius: '8px',
            fontSize: '0.9rem', boxShadow: '0 4px 12px rgba(0,0,0,0.15)'
          }}>{toast.msg}</div>
        )}

        <div className="top-bar">
          <div className="page-title">
            <h1>Settings</h1>
            <p>Manage your account preferences, notifications, and security</p>
          </div>
          <div className="user-info">
            <div className="user-avatar">
              {user ? (user.first_name?.[0] || user.username?.[0] || 'U').toUpperCase() : 'U'}
            </div>
            <div className="user-details">
              <h3>{user ? ((user.first_name || '') + ' ' + (user.last_name || '')).trim() || user.username : 'Ã¢â‚¬â€'}</h3>
              <p><i className="fas fa-briefcase"></i> {user?.role || 'Transporter'}</p>
            </div>
          </div>
        </div>

        <div className="settings-container">
          <div className="settings-sidebar">
            <ul className="settings-menu">
              {menuItems.map(item => (
                <li key={item.id} className="settings-menu-item">
                  <a href={`#${item.id}`}
                    className={`settings-menu-link${section === item.id ? ' active' : ''}`}
                    onClick={e => { e.preventDefault(); setSection(item.id) }}>
                    <i className={`fas ${item.icon}`}></i>{item.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          <div className="settings-content">

            {section === 'account' && (
              <div className="settings-section">
                <div className="section-header">
                  <h3><i className="fas fa-user-cog"></i> Account Settings</h3>
                  <p>Update your account information and profile details</p>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Full Name / Company</label>
                    <input type="text" className="form-control" value={account.companyName}
                      onChange={e => setAccount(p => ({ ...p, companyName: e.target.value }))} placeholder="Enter name" />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Email Address <span style={{ color: '#94a3b8', fontSize: '0.78rem' }}>(read-only)</span></label>
                    <input type="email" className="form-control" value={account.email} readOnly style={{ background: '#f8fafc' }} />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Phone Number</label>
                    <input type="tel" className="form-control" value={account.phone}
                      onChange={e => setAccount(p => ({ ...p, phone: e.target.value }))} placeholder="+92 300 0000000" />
                  </div>
                  <div className="form-group">
                    <label className="form-label">City / Address</label>
                    <input type="text" className="form-control" value={account.address}
                      onChange={e => setAccount(p => ({ ...p, address: e.target.value }))} placeholder="Enter city or address" />
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">About Your Business</label>
                  <textarea className="form-control" rows="4" value={account.about}
                    onChange={e => setAccount(p => ({ ...p, about: e.target.value }))} placeholder="Describe your business..."></textarea>
                </div>
                <div className="btn-group">
                  <button type="button" className="btn btn-primary" onClick={saveAccount} disabled={saving}>
                    <i className="fas fa-save"></i> {saving ? 'Saving...' : 'Save Changes'}
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => window.location.reload()}>
                    <i className="fas fa-undo"></i> Reset
                  </button>
                </div>
              </div>
            )}

            {section === 'notifications' && (
              <div className="settings-section">
                <div className="section-header">
                  <h3><i className="fas fa-bell"></i> Notification Settings</h3>
                  <p>Control how and when you receive notifications</p>
                </div>
                {[
                  { key: 'email', label: 'Email Notifications', desc: 'Receive notifications via email' },
                  { key: 'sms',   label: 'SMS Notifications',   desc: 'Get important alerts via SMS' },
                  { key: 'whatsapp', label: 'WhatsApp Notifications', desc: 'Receive time-critical dispatch alerts on WhatsApp' },
                  { key: 'push',  label: 'Push Notifications',  desc: 'Receive real-time browser updates' },
                ].map(item => (
                  <div key={item.key} className="toggle-item">
                    <div className="toggle-label"><strong>{item.label}</strong><p className="form-text">{item.desc}</p></div>
                    <label className="toggle-switch">
                      <input type="checkbox" checked={notifs[item.key]}
                        onChange={e => setNotifs(p => ({ ...p, [item.key]: e.target.checked }))} />
                      <span className="toggle-slider"></span>
                    </label>
                  </div>
                ))}
                <h4 style={{ margin: '25px 0 15px 0', color: 'var(--text-primary)', fontWeight: 600 }}>Notification Types</h4>
                {[
                  { key: 'jobAlerts', label: 'New Job Alerts',    desc: 'Get notified when matching jobs are posted' },
                  { key: 'payments',  label: 'Payment Updates',   desc: 'Notifications for payments and withdrawals' },
                  { key: 'system',    label: 'System Updates',    desc: 'Platform updates and new features' },
                  { key: 'promo',     label: 'Promotional Offers',desc: 'Receive offers and discounts' },
                ].map(item => (
                  <div key={item.key} className="toggle-item">
                    <div className="toggle-label"><strong>{item.label}</strong><p className="form-text">{item.desc}</p></div>
                    <label className="toggle-switch">
                      <input type="checkbox" checked={notifs[item.key]}
                        onChange={e => setNotifs(p => ({ ...p, [item.key]: e.target.checked }))} />
                      <span className="toggle-slider"></span>
                    </label>
                  </div>
                ))}
                <div className="btn-group">
                  <button type="button" className="btn btn-primary" onClick={saveNotifications} disabled={saving}>
                    <i className="fas fa-save"></i> {saving ? 'Saving...' : 'Save Preferences'}
                  </button>
                </div>
              </div>
            )}

            {section === 'privacy' && (
              <div className="settings-section">
                <div className="section-header">
                  <h3><i className="fas fa-shield-alt"></i> Privacy &amp; Security</h3>
                  <p>Manage your privacy settings and account security</p>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">New Password</label>
                    <input type="password" className="form-control" value={security.newPassword}
                      onChange={e => setSecurity(p => ({ ...p, newPassword: e.target.value }))} placeholder="Enter new password" />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Confirm Password</label>
                    <input type="password" className="form-control" value={security.confirmPassword}
                      onChange={e => setSecurity(p => ({ ...p, confirmPassword: e.target.value }))} placeholder="Confirm new password" />
                  </div>
                </div>
                {otpSent && (
                  <div className="form-row">
                    <div className="form-group">
                      <label className="form-label">Email OTP</label>
                      <input type="text" className="form-control" inputMode="numeric" maxLength="6"
                        value={otpCode} onChange={e => setOtpCode(e.target.value)} placeholder="Enter 6 digit OTP" />
                    </div>
                  </div>
                )}
                <p className="form-text" style={{ marginBottom: '20px' }}>
                  {otpSent
                    ? 'OTP sent to your email. Enter it above then click Verify & Update.'
                    : 'Enter a new password and click Update Security to receive an OTP on your email.'}
                </p>
                <div style={{ marginBottom: '20px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '10px', padding: '1rem' }}>
                  <h4 style={{ marginBottom: '8px', color: 'var(--text-primary)' }}>Fast Login MPIN</h4>
                  <p className="form-text" style={{ marginBottom: '12px' }}>
                    Optional 4 digit MPIN for the last logged-in account on this device.
                  </p>
                  <div className="form-row">
                    <div className="form-group">
                      <label className="form-label">4 Digit MPIN</label>
                      <input
                        type="password"
                        className="form-control"
                        inputMode="numeric"
                        maxLength="4"
                        value={mpinForm.mpin}
                        onChange={e => setMpinForm(p => ({ ...p, mpin: e.target.value.replace(/\D/g, '').slice(0, 4) }))}
                        placeholder="Enter 4 digits"
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Confirm MPIN</label>
                      <input
                        type="password"
                        className="form-control"
                        inputMode="numeric"
                        maxLength="4"
                        value={mpinForm.confirmMpin}
                        onChange={e => setMpinForm(p => ({ ...p, confirmMpin: e.target.value.replace(/\D/g, '').slice(0, 4) }))}
                        placeholder="Re-enter 4 digits"
                      />
                    </div>
                  </div>
                  <div className="btn-group">
                    <button type="button" className="btn btn-primary" onClick={saveMpin} disabled={saving}>
                      <i className="fas fa-lock"></i> {user?.mpin_enabled ? 'Update MPIN' : 'Enable MPIN'}
                    </button>
                    {user?.mpin_enabled && (
                      <button type="button" className="btn btn-secondary" onClick={disableMpin} disabled={saving}>
                        <i className="fas fa-lock-open"></i> Disable MPIN
                      </button>
                    )}
                  </div>
                </div>
                <div className="settings-cards">
                  <div className="settings-card" style={{ cursor: 'pointer' }}
                    onClick={() => showToast('Data download request submitted. You will receive an email.')}>
                    <div className="settings-card-icon"><i className="fas fa-download"></i></div>
                    <h4>Download Your Data</h4>
                    <p>Request a copy of all your personal data</p>
                  </div>
                  <div className="settings-card" style={{ cursor: 'pointer' }}
                    onClick={() => { if (window.confirm('Permanently delete your account? This cannot be undone.')) showToast('Account deletion request submitted.', 'error') }}>
                    <div className="settings-card-icon"><i className="fas fa-trash-alt"></i></div>
                    <h4>Delete Account</h4>
                    <p>Permanently delete your account and all data</p>
                  </div>
                </div>
                {activityLogs.length > 0 && (
                  <div style={{ marginTop: '20px', background: '#f8fafc', borderRadius: '8px', padding: '1rem' }}>
                    <h4 style={{ marginBottom: '10px', color: 'var(--text-primary)' }}>Recent Login Activity</h4>
                    {activityLogs.map((log, i) => (
                      <div key={i} style={{ fontSize: '0.85rem', color: '#64748b', padding: '0.3rem 0', borderBottom: '1px solid #e2e8f0' }}>
                        <i className="fas fa-circle" style={{ fontSize: '0.5rem', marginRight: '8px', color: '#22c55e' }}></i>
                        {log.created_at} Ã¢â‚¬â€ {log.ip_address || 'Unknown IP'}
                      </div>
                    ))}
                  </div>
                )}
                <div className="btn-group">
                  <button type="button" className="btn btn-primary" onClick={updateSecurity} disabled={saving}>
                    <i className="fas fa-save"></i> {saving ? 'Processing...' : (otpSent ? 'Verify & Update' : 'Update Security')}
                  </button>
                  {otpSent && (
                    <button type="button" className="btn btn-secondary" onClick={resendOtp} disabled={saving}>
                      <i className="fas fa-paper-plane"></i> Resend OTP
                    </button>
                  )}
                  <button type="button" className="btn btn-secondary" onClick={viewLoginActivity}>
                    <i className="fas fa-history"></i> View Login Activity
                  </button>
                </div>
              </div>
            )}

            {section === 'preferences' && (
              <div className="settings-section">
                <div className="section-header">
                  <h3><i className="fas fa-sliders-h"></i> Preferences</h3>
                  <p>Customize your Digi_TransX experience</p>
                </div>
                {[
                  { id: 'language', label: 'Language', options: [{ val: 'en', label: 'English' }, { val: 'ur', label: 'Urdu' }, { val: 'hi', label: 'Hindi' }] },
                  { id: 'currency', label: 'Currency', options: [{ val: 'PKR', label: 'Pakistani Rupee (PKR)' }, { val: 'USD', label: 'US Dollar ($)' }, { val: 'EUR', label: 'Euro (EUR)' }] },
                  { id: 'timezone', label: 'Timezone', options: [{ val: 'PKT', label: 'Pakistani Standard Time (PKT)' }, { val: 'UTC', label: 'UTC' }, { val: 'EST', label: 'Eastern Standard Time' }] },
                ].map(field => (
                  <div key={field.id} className="form-group">
                    <label className="form-label">{field.label}</label>
                    <div className="select-wrapper">
                      <select className="form-control" value={prefs[field.id]}
                        onChange={e => setPrefs(p => ({ ...p, [field.id]: e.target.value }))}>
                        {field.options.map(o => <option key={o.val} value={o.val}>{o.label}</option>)}
                      </select>
                      <i className="fas fa-chevron-down"></i>
                    </div>
                  </div>
                ))}
                <div className="form-group">
                  <label className="form-label">Date Format</label>
                  <div className="radio-group">
                    {[{ val: 'DD/MM/YYYY' }, { val: 'MM/DD/YYYY' }, { val: 'YYYY-MM-DD' }].map(f => (
                      <div key={f.val} className="radio-item">
                        <input type="radio" id={`df-${f.val}`} name="dateFormat" value={f.val}
                          checked={prefs.dateFormat === f.val} onChange={e => setPrefs(p => ({ ...p, dateFormat: e.target.value }))} />
                        <label htmlFor={`df-${f.val}`}>{f.val}</label>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">Theme</label>
                  <div className="radio-group">
                    {['light', 'dark', 'auto'].map(t => (
                      <div key={t} className="radio-item">
                        <input type="radio" id={`theme-${t}`} name="theme" value={t}
                          checked={prefs.theme === t} onChange={e => setPrefs(p => ({ ...p, theme: e.target.value }))} />
                        <label htmlFor={`theme-${t}`}>{t.charAt(0).toUpperCase() + t.slice(1)}</label>
                      </div>
                    ))}
                  </div>
                </div>
                {[
                  { key: 'autoRefresh', label: 'Auto-refresh Dashboard', desc: 'Automatically refresh dashboard data every 5 minutes' },
                  { key: 'tips',        label: 'Show Tutorial Tips',      desc: 'Display helpful tips for new features' },
                ].map(item => (
                  <div key={item.key} className="toggle-item">
                    <div className="toggle-label"><strong>{item.label}</strong><p className="form-text">{item.desc}</p></div>
                    <label className="toggle-switch">
                      <input type="checkbox" checked={prefs[item.key]}
                        onChange={e => setPrefs(p => ({ ...p, [item.key]: e.target.checked }))} />
                      <span className="toggle-slider"></span>
                    </label>
                  </div>
                ))}
                <div className="btn-group">
                  <button type="button" className="btn btn-primary" onClick={savePreferences} disabled={saving}>
                    <i className="fas fa-save"></i> {saving ? 'Saving...' : 'Save Preferences'}
                  </button>
                  <button type="button" className="btn btn-secondary"
                    onClick={() => setPrefs({ language: 'en', currency: 'PKR', timezone: 'PKT', dateFormat: 'DD/MM/YYYY', theme: 'light', autoRefresh: true, tips: false })}>
                    <i className="fas fa-undo"></i> Reset to Defaults
                  </button>
                </div>
              </div>
            )}

            {section === 'billing' && (
              <div className="settings-section">
                <div className="section-header">
                  <h3><i className="fas fa-credit-card"></i> Billing &amp; Payments</h3>
                  <p>Manage your payment methods and billing information</p>
                </div>
                <div className="settings-cards">
                  {[
                    { icon: 'fa-plus-circle', title: 'Add Payment Method', desc: 'Add a new bank account or UPI', action: () => navigate('/transporter/account-history') },
                    { icon: 'fa-file-invoice', title: 'View Invoices', desc: 'Access and download transaction invoices', action: () => navigate('/transporter/account-history') },
                    { icon: 'fa-percentage', title: 'Tax Settings', desc: 'Configure GST and other tax settings', action: () => showToast('Tax settings coming soon!') },
                  ].map(card => (
                    <div key={card.title} className="settings-card" style={{ cursor: 'pointer' }} onClick={card.action}>
                      <div className="settings-card-icon"><i className={`fas ${card.icon}`}></i></div>
                      <h4>{card.title}</h4>
                      <p>{card.desc}</p>
                    </div>
                  ))}
                </div>
                <h4 style={{ margin: '30px 0 15px 0', color: 'var(--text-primary)', fontWeight: 600 }}>Payment Settings</h4>
                {[
                  { key: 'autoWithdrawal', label: 'Auto-Withdrawal',       desc: 'Auto-transfer earnings to your bank every week' },
                  { key: 'invoiceAuto',    label: 'Invoice Auto-generation',desc: 'Auto-generate invoices for completed jobs' },
                ].map(item => (
                  <div key={item.key} className="toggle-item">
                    <div className="toggle-label"><strong>{item.label}</strong><p className="form-text">{item.desc}</p></div>
                    <label className="toggle-switch">
                      <input type="checkbox" checked={billing[item.key]}
                        onChange={e => setBilling(p => ({ ...p, [item.key]: e.target.checked }))} />
                      <span className="toggle-slider"></span>
                    </label>
                  </div>
                ))}
                <div className="btn-group">
                  <button type="button" className="btn btn-primary" onClick={() => navigate('/transporter/account-history')}>
                    <i className="fas fa-cog"></i> Manage Billing
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => navigate('/transporter/account-history')}>
                    <i className="fas fa-history"></i> Payment History
                  </button>
                </div>
              </div>
            )}

            {section === 'integrations' && (
              <div className="settings-section">
                <div className="section-header">
                  <h3><i className="fas fa-plug"></i> Integrations</h3>
                  <p>Connect Digi_TransX with other tools and services</p>
                </div>
                <div className="settings-cards">
                  <div className="settings-card">
                    <div className="settings-card-icon" style={{ background: 'linear-gradient(135deg, #4285F4, #34A853)' }}><i className="fas fa-map-marker-alt"></i></div>
                    <h4>Google Maps</h4>
                    <p>Route planning and real-time tracking</p>
                    <div style={{ marginTop: '15px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <label className="toggle-switch">
                        <input type="checkbox" checked={integrations.mapsEnabled}
                          onChange={e => setIntegrations(p => ({ ...p, mapsEnabled: e.target.checked }))} />
                        <span className="toggle-slider"></span>
                      </label>
                      <span style={{ fontSize: '14px', color: 'var(--text-muted)' }}>{integrations.mapsEnabled ? 'Connected' : 'Disabled'}</span>
                    </div>
                  </div>
                  <div className="settings-card">
                    <div className="settings-card-icon" style={{ background: 'linear-gradient(135deg, #FF6B6B, #FF8E53)' }}><i className="fas fa-file-excel"></i></div>
                    <h4>Export to Excel</h4>
                    <p>Export job history, earnings, and reports</p>
                    <div style={{ marginTop: '15px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <label className="toggle-switch">
                        <input type="checkbox" checked={integrations.excelExport}
                          onChange={e => setIntegrations(p => ({ ...p, excelExport: e.target.checked }))} />
                        <span className="toggle-slider"></span>
                      </label>
                      <span style={{ fontSize: '14px', color: 'var(--text-muted)' }}>{integrations.excelExport ? 'Enabled' : 'Disabled'}</span>
                    </div>
                  </div>
                  <div className="settings-card">
                    <div className="settings-card-icon" style={{ background: 'linear-gradient(135deg, #6A11CB, #2575FC)' }}><i className="fas fa-cloud"></i></div>
                    <h4>Cloud Storage</h4>
                    <p>Backup documents to Google Drive or Dropbox</p>
                    <div style={{ marginTop: '15px' }}>
                      <button type="button" className="btn btn-secondary" style={{ padding: '8px 15px', fontSize: '14px' }}
                        onClick={() => showToast('Cloud storage integration coming soon!')}>
                        <i className="fas fa-link"></i> Connect
                      </button>
                    </div>
                  </div>
                </div>
                <h4 style={{ margin: '30px 0 15px 0', color: 'var(--text-primary)', fontWeight: 600 }}>API Access</h4>
                <div className="form-group">
                  <label className="form-label">API Key</label>
                  <div style={{ display: 'flex', gap: '10px' }}>
                    <input type="text" className="form-control" value={apiKey} readOnly
                      placeholder="Click Generate New API Key" style={{ flex: 1, fontFamily: 'monospace', fontSize: '0.85rem' }} />
                    <button type="button" className="btn btn-secondary" style={{ padding: '8px 14px' }} onClick={copyApiKey} title="Copy API Key">
                      <i className="fas fa-copy"></i>
                    </button>
                  </div>
                </div>
                <div className="toggle-item">
                  <div className="toggle-label"><strong>Enable API Access</strong><p className="form-text">Allow external systems to access your data via API</p></div>
                  <label className="toggle-switch">
                    <input type="checkbox" checked={integrations.apiAccess}
                      onChange={e => setIntegrations(p => ({ ...p, apiAccess: e.target.checked }))} />
                    <span className="toggle-slider"></span>
                  </label>
                </div>
                <div className="btn-group">
                  <button type="button" className="btn btn-primary" onClick={generateApiKey}>
                    <i className="fas fa-key"></i> Generate New API Key
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => showToast('API documentation coming soon!')}>
                    <i className="fas fa-book"></i> API Documentation
                  </button>
                </div>
              </div>
            )}

            {section === 'advanced' && (
              <div className="settings-section">
                <div className="section-header">
                  <h3><i className="fas fa-tools"></i> Advanced Settings</h3>
                  <p>Advanced configuration options for power users</p>
                </div>
                {[
                  { id: 'cacheSize', label: 'Cache Size', options: [{ val: 'small', label: 'Small (50 MB)' }, { val: 'medium', label: 'Medium (100 MB)' }, { val: 'large', label: 'Large (250 MB)' }, { val: 'unlimited', label: 'Unlimited' }] },
                  { id: 'dataRetention', label: 'Data Retention Period', options: [{ val: '30', label: '30 days' }, { val: '90', label: '90 days' }, { val: '180', label: '180 days' }, { val: '365', label: '1 year' }, { val: 'forever', label: 'Forever' }] },
                ].map(field => (
                  <div key={field.id} className="form-group">
                    <label className="form-label">{field.label}</label>
                    <div className="select-wrapper">
                      <select className="form-control" value={advanced[field.id]}
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
                  <div key={item.key} className="toggle-item">
                    <div className="toggle-label"><strong>{item.label}</strong><p className="form-text">{item.desc}</p></div>
                    <label className="toggle-switch">
                      <input type="checkbox" checked={advanced[item.key]}
                        onChange={e => setAdvanced(p => ({ ...p, [item.key]: e.target.checked }))} />
                      <span className="toggle-slider"></span>
                    </label>
                  </div>
                ))}
                <h4 style={{ margin: '30px 0 15px 0', color: 'var(--text-primary)', fontWeight: 600 }}>System Actions</h4>
                <div className="btn-group">
                  <button type="button" className="btn btn-secondary"
                    onClick={() => { try { localStorage.clear() } catch { /* ignore unavailable storage */ } showToast('Cache cleared!') }}>
                    <i className="fas fa-broom"></i> Clear Cache
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => window.location.reload()}>
                    <i className="fas fa-sync-alt"></i> Refresh All Data
                  </button>
                  <button type="button" className="btn btn-danger"
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

        <div className="footer">
          <p>&copy; 2026 Digi_TransX Transport Services. All rights reserved.</p>
          <div className="footer-links">
            <Link to="/transporter/about">About Us</Link>
            <Link to="/transporter/contact">Contact</Link>
            <Link to="/transporter/terms">Terms &amp; Conditions</Link>
            <Link to="/transporter/privacy">Privacy Policy</Link>
            <Link to="/transporter/help">Help Center</Link>
            <Link to="/transporter/partner">Partner With Us</Link>
          </div>
        </div>
        <div className="notification-panel" id="notificationPanel"></div>
      </div>
    
  )
}
