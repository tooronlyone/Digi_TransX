import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import AuthCard from '../../components/common/AuthCard'
import InputField from '../../components/common/InputField'
import Notification from '../../components/common/Notification'

const STEPS = { REQUEST: 'request', VERIFY: 'verify', RESET: 'reset', DONE: 'done' }

export default function ResetPassword() {
  const [step, setStep] = useState(STEPS.REQUEST)
  const [loginId, setLoginId] = useState('')
  const [otp, setOtp] = useState('')
  const [resetToken, setResetToken] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const [notification, setNotification] = useState({ type: '', message: '' })
  const [maskedEmail, setMaskedEmail] = useState('')

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const id = params.get('loginId')
    if (id) setLoginId(id)
    const token = params.get('token')
    if (token) {
      setResetToken(token)
      setStep(STEPS.RESET)
    }
  }, [])

  async function handleRequest(event) {
    event.preventDefault()
    if (!loginId.trim()) {
      setErrors({ loginId: 'Email or CNIC is required' })
      return
    }

    setErrors({})
    setLoading(true)
    try {
      const response = await fetch('/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ loginId: loginId.trim() }),
      })
      const data = await response.json()
      if (response.ok && data.success) {
        setMaskedEmail(data.masked_email || '')
        setNotification({ type: 'success', message: data.message || 'OTP sent to your registered email.' })
        setStep(STEPS.VERIFY)
      } else {
        setNotification({ type: 'error', message: data.message || 'Request failed.' })
      }
    } catch (_) {
      setNotification({ type: 'error', message: 'Network error. Please try again.' })
    } finally {
      setLoading(false)
    }
  }

  async function handleVerify(event) {
    event.preventDefault()
    if (!otp.trim()) {
      setErrors({ otp: 'OTP is required' })
      return
    }

    setErrors({})
    setLoading(true)
    try {
      const response = await fetch('/auth/password-reset/verify-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ loginId: loginId.trim(), otp: otp.trim() }),
      })
      const data = await response.json()
      if (response.ok && data.success) {
        setResetToken(data.reset_token || '')
        setNotification({ type: 'success', message: 'OTP verified. Set your new password.' })
        setStep(STEPS.RESET)
      } else {
        setNotification({ type: 'error', message: data.message || 'Invalid OTP.' })
      }
    } catch (_) {
      setNotification({ type: 'error', message: 'Network error.' })
    } finally {
      setLoading(false)
    }
  }

  async function handleReset(event) {
    event.preventDefault()
    const nextErrors = {}
    if (!password) nextErrors.password = 'Password is required'
    else if (password.length < 8) nextErrors.password = 'Password must be at least 8 characters'
    if (password !== confirmPassword) nextErrors.confirmPassword = 'Passwords do not match'
    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors)
      return
    }

    setErrors({})
    setLoading(true)
    try {
      const response = await fetch('/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ reset_token: resetToken, new_password: password }),
      })
      const data = await response.json()
      if (response.ok && data.success) {
        setNotification({ type: 'success', message: 'Password reset successful.' })
        setStep(STEPS.DONE)
      } else {
        setNotification({ type: 'error', message: data.message || 'Reset failed.' })
      }
    } catch (_) {
      setNotification({ type: 'error', message: 'Network error.' })
    } finally {
      setLoading(false)
    }
  }

  const stepTitles = {
    [STEPS.REQUEST]: 'Reset your password',
    [STEPS.VERIFY]: 'Verify your email',
    [STEPS.RESET]: 'Set new password',
    [STEPS.DONE]: 'Password reset complete',
  }

  return (
    <AuthCard title={stepTitles[step]} subtitle="Account recovery">
      <Notification
        type={notification.type}
        message={notification.message}
        onClose={() => setNotification({ type: '', message: '' })}
      />

      {step === STEPS.REQUEST && (
        <form onSubmit={handleRequest}>
          <InputField
            label="Email or CNIC"
            id="loginId"
            type="text"
            placeholder="Enter your email or 13 digit CNIC"
            value={loginId}
            onChange={event => setLoginId(event.target.value)}
            error={errors.loginId}
          />
          <p className="text-gray-400 text-xs mb-5">
            DigiTransX will send a 6 digit code to the registered email linked with this account.
          </p>
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-blue-500 hover:bg-blue-600 disabled:bg-gray-400 text-white font-semibold rounded-lg transition-colors flex items-center justify-center gap-2"
          >
            {loading && <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
            {loading ? 'Sending...' : 'Request reset'}
          </button>
          <div className="text-center mt-4">
            <Link to="/login" className="text-gray-500 text-sm hover:text-blue-500 hover:underline">Back to login</Link>
          </div>
        </form>
      )}

      {step === STEPS.VERIFY && (
        <form onSubmit={handleVerify}>
          {maskedEmail && (
            <p className="text-gray-600 text-sm mb-4">
              Enter the 6 digit code sent to <strong>{maskedEmail}</strong>
            </p>
          )}
          <InputField
            label="Verification Code"
            id="otp"
            type="text"
            placeholder="Enter 6 digit OTP"
            maxLength={6}
            value={otp}
            onChange={event => setOtp(event.target.value.replace(/\D/g, '').slice(0, 6))}
            error={errors.otp}
          />
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-blue-500 hover:bg-blue-600 disabled:bg-gray-400 text-white font-semibold rounded-lg transition-colors flex items-center justify-center gap-2"
          >
            {loading && <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
            {loading ? 'Verifying...' : 'Verify code'}
          </button>
          <div className="text-center mt-4">
            <button
              type="button"
              onClick={() => setStep(STEPS.REQUEST)}
              className="text-gray-500 text-sm hover:text-blue-500 hover:underline bg-transparent border-none cursor-pointer"
            >
              Try a different account
            </button>
          </div>
        </form>
      )}

      {step === STEPS.RESET && (
        <form onSubmit={handleReset}>
          <InputField
            label="New Password"
            id="password"
            type="password"
            placeholder="Create a strong password"
            value={password}
            onChange={event => setPassword(event.target.value)}
            error={errors.password}
          />
          <InputField
            label="Confirm Password"
            id="confirmPassword"
            type="password"
            placeholder="Confirm your new password"
            value={confirmPassword}
            onChange={event => setConfirmPassword(event.target.value)}
            error={errors.confirmPassword}
          />
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-blue-500 hover:bg-blue-600 disabled:bg-gray-400 text-white font-semibold rounded-lg transition-colors flex items-center justify-center gap-2"
          >
            {loading && <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
            {loading ? 'Saving...' : 'Save new password'}
          </button>
        </form>
      )}

      {step === STEPS.DONE && (
        <div className="text-center py-4">
          <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <span className="text-green-500 text-3xl">OK</span>
          </div>
          <p className="text-gray-600 mb-6">Your password has been reset successfully.</p>
          <Link
            to="/login"
            className="block w-full py-3 bg-blue-500 hover:bg-blue-600 text-white font-semibold rounded-lg transition-colors text-center"
          >
            Back to Login
          </Link>
        </div>
      )}
    </AuthCard>
  )
}
