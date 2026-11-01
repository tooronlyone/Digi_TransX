import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'

const SUBJECTS = [
  'Truck Registration Issue',
  'Payment Problem',
  'Booking / Order Issue',
  'Account or Login Problem',
  'Dashboard or App Bug',
  'Document Upload Issue',
  'Driver or Route Complaint',
  'General Inquiry',
  'Other',
]

const supportChannels = [
  { icon: 'fas fa-headset', title: '24/7 Helpline', description: '+1 (555) 123-4567' },
  { icon: 'fas fa-envelope-open-text', title: 'Email Support', description: 'support@digitransx.com' },
  { icon: 'fas fa-truck-fast', title: 'Dispatch Desk', description: 'dispatch@digitransx.com' },
]

const officeLocations = [
  { icon: 'fas fa-building', title: 'Head Office', address: '1234 Transport Lane, Logistics City', hours: 'Mon-Sat, 9:00 AM - 6:00 PM' },
  { icon: 'fas fa-warehouse', title: 'Operations Hub', address: '78 Cargo Avenue, Freight District', hours: '24/7 dispatch coordination' },
]

const faqs = [
  { question: 'How quickly does Digi_TransX support respond?', answer: 'Most transporter support tickets receive an initial response within 24 hours. Urgent operational issues are prioritized faster on the helpline and dispatch desk.' },
  { question: 'Can I get help with truck, payment, or booking issues here?', answer: 'Yes. This page is the main support entry point for truck setup, booking status, payment questions, dashboard issues, and account assistance.' },
  { question: 'Is live chat available all day?', answer: 'Live chat is available for quick guidance throughout the day, while helpline and dispatch escalation remain available for urgent transport operations.' },
  { question: 'What details should I include in my message?', answer: 'Include your truck number, route or booking reference, issue summary, and any payment or timing context. That reduces back-and-forth and speeds up resolution.' },
]

export default function Contact() {
  const api = useApi()
  const [activeFaq, setActiveFaq] = useState(0)
  const [isChatOpen, setIsChatOpen] = useState(false)
  const [chatMessages, setChatMessages] = useState([
    { from: 'support', text: 'Assalam o Alaikum. How can Digi_TransX support help you today?', time: 'Support - now' },
  ])
  const [chatInput, setChatInput] = useState('')

  const [form, setForm] = useState({ name: '', email: '', phone: '', subject: '', message: '', agree: false })
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [formError, setFormError] = useState('')

  function setField(e) {
    const { name, value, type, checked } = e.target
    setForm(f => ({ ...f, [name]: type === 'checkbox' ? checked : value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setFormError('')
    if (!form.name.trim()) { setFormError('Full name is required'); return }
    if (!form.email.trim()) { setFormError('Email address is required'); return }
    if (!form.subject) { setFormError('Please select a subject'); return }
    if (!form.message.trim()) { setFormError('Message cannot be empty'); return }
    if (!form.agree) { setFormError('You must agree to the terms'); return }
    setSubmitting(true)
    try {
      await api.post('/api/contact', {
        name: form.name, email: form.email,
        phone: form.phone, subject: form.subject, message: form.message,
      })
      setSubmitted(true)
    } catch {
      setFormError('Failed to send message. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  function sendChat() {
    const text = chatInput.trim()
    if (!text) return
    const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    setChatMessages(prev => [...prev, { from: 'user', text, time: `You - ${now}` }])
    setChatInput('')
    setTimeout(() => {
      setChatMessages(prev => [...prev, {
        from: 'support',
        text: 'Thank you for your message. Our support agent will respond shortly. For urgent issues, please call our helpline.',
        time: `Support - ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`,
      }])
    }, 1000)
  }

  function handleChatKey(e) {
    if (e.key === 'Enter') sendChat()
  }

  return (
      <div className="page-contact">
        <div className="page-title">
          <h1>Contact Us</h1>
          <p>Get in touch with our support team for any queries or assistance</p>
        </div>

        <div className="contact-grid">
          <div className="contact-form-section">
            <div className="form-header">
              <h2><i className="fas fa-paper-plane"></i> Send us a Message</h2>
              <p>We'll get back to you within 24 hours</p>
            </div>

            {submitted ? (
              <div style={{ textAlign: 'center', padding: '40px 20px', background: '#d4edda', borderRadius: 12, border: '1px solid #28a745' }}>
                <i className="fas fa-check-circle" style={{ fontSize: 48, color: '#27ae60', marginBottom: 16 }}></i>
                <h3 style={{ color: '#27ae60', marginBottom: 8 }}>Message Sent!</h3>
                <p style={{ color: '#155724' }}>Thank you, {form.name}. We'll respond to {form.email} within 24 hours.</p>
                <button className="submit-btn" style={{ marginTop: 20 }} onClick={() => { setSubmitted(false); setForm({ name: '', email: '', phone: '', subject: '', message: '', agree: false }) }}>
                  Send Another Message
                </button>
              </div>
            ) : (
              <form className="contact-form" onSubmit={handleSubmit} noValidate>
                {formError && (
                  <div style={{ color: '#e74c3c', background: '#ffeaea', border: '1px solid #e74c3c', borderRadius: 8, padding: '10px 14px', marginBottom: 16, fontSize: 14 }}>
                    <i className="fas fa-exclamation-circle"></i> {formError}
                  </div>
                )}

                <div className="form-group">
                  <label htmlFor="name"><i className="fas fa-user"></i> Full Name</label>
                  <input type="text" id="name" name="name" value={form.name} onChange={setField}
                    placeholder="Enter your full name" required />
                </div>

                <div className="form-group">
                  <label htmlFor="email"><i className="fas fa-envelope"></i> Email Address</label>
                  <input type="email" id="email" name="email" value={form.email} onChange={setField}
                    placeholder="Enter your email" required />
                </div>

                <div className="form-group">
                  <label htmlFor="phone"><i className="fas fa-phone"></i> Phone Number</label>
                  <input type="tel" id="phone" name="phone" value={form.phone} onChange={setField}
                    placeholder="Enter your phone number" />
                </div>

                <div className="form-group">
                  <label htmlFor="subject"><i className="fas fa-tag"></i> Subject</label>
                  <select id="subject" name="subject" value={form.subject} onChange={setField} required>
                    <option value="" disabled>Select an issue type</option>
                    {SUBJECTS.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>

                <div className="form-group">
                  <label htmlFor="message"><i className="fas fa-comment-dots"></i> Message</label>
                  <textarea id="message" name="message" value={form.message} onChange={setField}
                    rows={5} placeholder="Describe your issue or query in detail..." required />
                </div>

                <div className="form-group">
                  <label className="checkbox-container">
                    <input type="checkbox" name="agree" checked={form.agree} onChange={setField} required />
                    <span className="checkmark"></span>
                    I agree to the terms and conditions
                  </label>
                </div>

                <button type="submit" className="submit-btn" disabled={submitting}>
                  <i className="fas fa-paper-plane"></i> {submitting ? 'Sending...' : 'Send Message'}
                </button>
              </form>
            )}
          </div>

          <div className="contact-info-section">
            <div className="contact-info-card">
              <h3><i className="fas fa-map-marker-alt"></i> Our Headquarters</h3>
              <p>1234 Transport Lane, Logistics City, Country</p>
              <p><i className="fas fa-phone"></i> +1 (555) 123-4567</p>
              <p><i className="fas fa-envelope"></i> info@digitransx.com</p>
            </div>

            <div className="support-channels">
              <h3 className="info-section-title">Support Channels</h3>
              {supportChannels.map(ch => (
                <div className="support-channel" key={ch.title}>
                  <div className="support-icon"><i className={ch.icon}></i></div>
                  <div className="support-details"><h4>{ch.title}</h4><p>{ch.description}</p></div>
                </div>
              ))}
            </div>

            <div className="office-locations">
              <h3 className="info-section-title">Office Locations</h3>
              {officeLocations.map(office => (
                <div className="office-card" key={office.title}>
                  <div className="office-icon"><i className={office.icon}></i></div>
                  <div className="office-info">
                    <h4>{office.title}</h4>
                    <p>{office.address}</p>
                    <p>{office.hours}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="live-chat-card">
              <div className="chat-header">
                <h3><i className="fas fa-comment-dots"></i> Live Chat Support</h3>
                <span className="status-indicator active"></span>
              </div>
              <p>Chat with our support agents in real-time</p>
              <button className="chat-btn" onClick={() => setIsChatOpen(true)}>
                <i className="fas fa-comment"></i> Start Live Chat
              </button>
              <p className="chat-availability">Available: 24/7</p>
            </div>
          </div>
        </div>

        <div className="faq-section">
          <h2 className="section-title">Frequently Asked Questions</h2>
          <div className="faq-grid">
            {faqs.map((faq, index) => {
              const isActive = activeFaq === index
              return (
                <div className={`faq-item${isActive ? ' active' : ''}`} key={faq.question}>
                  <button
                    type="button" className="faq-question"
                    aria-expanded={isActive}
                    onClick={() => setActiveFaq(isActive ? -1 : index)}
                  >
                    <span>{faq.question}</span>
                    <i className={`fas fa-chevron-${isActive ? 'up' : 'down'}`}></i>
                  </button>
                  {isActive && (
                    <div className="faq-answer">
                      <p>{faq.answer}</p>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {isChatOpen && (
          <div className="chat-modal active" style={{ position: 'fixed', inset: 0, zIndex: 9990, display: 'flex', alignItems: 'flex-end', justifyContent: 'flex-end', padding: 24 }}>
            <div className="chat-modal-content" style={{ width: 360, maxHeight: '70vh', display: 'flex', flexDirection: 'column', background: 'var(--card-bg)', borderRadius: 16, boxShadow: '0 8px 32px rgba(0,0,0,0.3)' }}>
              <div className="chat-header" style={{ padding: '14px 18px', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ margin: 0, fontSize: 16 }}><i className="fas fa-comment-dots"></i> Live Chat Support</h3>
                <button onClick={() => setIsChatOpen(false)} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: 'var(--text-secondary)' }}>&times;</button>
              </div>
              <div className="chat-messages" style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
                {chatMessages.map((msg, i) => (
                  <div key={i} className={`chat-message ${msg.from}`} style={{ alignSelf: msg.from === 'user' ? 'flex-end' : 'flex-start', maxWidth: '80%' }}>
                    <div className="message-bubble" style={{
                      background: msg.from === 'user' ? 'var(--primary)' : 'var(--hover-bg)',
                      color: msg.from === 'user' ? '#fff' : 'var(--text-primary)',
                      padding: '10px 14px', borderRadius: 12,
                    }}>{msg.text}</div>
                    <span className="message-time" style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'block', marginTop: 4 }}>{msg.time}</span>
                  </div>
                ))}
              </div>
              <div className="chat-input" style={{ padding: 12, borderTop: '1px solid var(--border-color)', display: 'flex', gap: 8 }}>
                <input
                  type="text"
                  placeholder="Type your message..."
                  value={chatInput}
                  onChange={e => setChatInput(e.target.value)}
                  onKeyDown={handleChatKey}
                  style={{ flex: 1, padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border-color)', background: 'var(--input-bg)', color: 'var(--text-primary)' }}
                />
                <button onClick={sendChat} style={{ background: 'var(--primary)', color: '#fff', border: 'none', borderRadius: 8, padding: '8px 14px', cursor: 'pointer' }}>
                  <i className="fas fa-paper-plane"></i>
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    
  )
}
