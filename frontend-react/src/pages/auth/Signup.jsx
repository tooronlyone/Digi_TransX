import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import AuthCard from '../../components/common/AuthCard'
import InputField from '../../components/common/InputField'
import Notification from '../../components/common/Notification'

function getPasswordStrength(password) {
  let score = 0
  if (password.length >= 8) score++
  if (/[A-Z]/.test(password)) score++
  if (/[0-9]/.test(password)) score++
  if (/[^A-Za-z0-9]/.test(password)) score++
  return score
}

const strengthLabels = ['', 'Weak', 'Fair', 'Good', 'Strong']
const strengthColors = ['', 'bg-red-400', 'bg-yellow-400', 'bg-blue-400', 'bg-green-500']

export default function Signup() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', email: '', phone: '', password: '', cnic: '' })
  const [errors, setErrors] = useState({})
  const [notification, setNotification] = useState({ type: '', message: '' })
  const strength = getPasswordStrength(form.password)

  function validate() {
    const nextErrors = {}
    if (!form.name.trim()) nextErrors.name = 'Full name is required'
    if (!form.email) nextErrors.email = 'Email is required'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) nextErrors.email = 'Invalid email address'
    if (!form.phone) nextErrors.phone = 'Phone number is required'
    else if (!/^\d{10,15}$/.test(form.phone.replace(/\D/g, ''))) nextErrors.phone = 'Enter a valid phone (10-15 digits)'
    if (!form.password) nextErrors.password = 'Password is required'
    else if (form.password.length < 8) nextErrors.password = 'Password must be at least 8 characters'
    if (!form.cnic.trim()) nextErrors.cnic = 'CNIC is required'
    else if (!/^\d{13}$/.test(form.cnic.replace(/\D/g, ''))) nextErrors.cnic = 'CNIC must be 13 digits'
    return nextErrors
  }

  function handleNext(event) {
    event.preventDefault()
    const nextErrors = validate()
    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors)
      return
    }

    setErrors({})
    sessionStorage.setItem(
      'signup_basic',
      JSON.stringify({
        name: form.name.trim(),
        email: form.email.trim().toLowerCase(),
        phone: form.phone.trim(),
        password: form.password,
        cnic: form.cnic.trim(),
      })
    )
    navigate('/signup/role')
  }

  const setField = (field) => (event) => setForm(current => ({ ...current, [field]: event.target.value }))

  return (
    <AuthCard title="Create Account" subtitle="Join DigiTransX - Pakistan's transport platform">
      <Notification
        type={notification.type}
        message={notification.message}
        onClose={() => setNotification({ type: '', message: '' })}
      />

      <form onSubmit={handleNext}>
        <InputField
          label="Full Name"
          id="name"
          type="text"
          placeholder="Enter your full name"
          value={form.name}
          onChange={setField('name')}
          error={errors.name}
        />

        <InputField
          label="Email Address"
          id="email"
          type="email"
          placeholder="Enter your email"
          value={form.email}
          onChange={setField('email')}
          error={errors.email}
        />

        <InputField
          label="Phone Number"
          id="phone"
          type="tel"
          placeholder="03XX-XXXXXXX"
          value={form.phone}
          onChange={setField('phone')}
          error={errors.phone}
        />

        <div className="mb-5">
          <label htmlFor="password" className="block mb-2 font-semibold text-gray-700 text-sm">Password</label>
          <input
            id="password"
            type="password"
            placeholder="Create a strong password"
            value={form.password}
            onChange={setField('password')}
            className={`w-full px-4 py-3 border-2 rounded-lg text-base transition-all outline-none
              focus:border-blue-400 focus:ring-2 focus:ring-blue-100
              ${errors.password ? 'border-red-400' : 'border-gray-200'}`}
          />
          {form.password && (
            <div className="mt-2">
              <div className="flex gap-1 h-1.5">
                {[1, 2, 3, 4].map(index => (
                  <div
                    key={index}
                    className={`flex-1 rounded-full transition-all ${index <= strength ? strengthColors[strength] : 'bg-gray-200'}`}
                  />
                ))}
              </div>
              <p className="text-xs mt-1 text-gray-500">{strengthLabels[strength]}</p>
            </div>
          )}
          {errors.password && <p className="text-red-500 text-xs mt-1">{errors.password}</p>}
          <p className="text-gray-400 text-xs mt-1">At least 8 characters with letters and numbers</p>
        </div>

        <div className="mb-6">
          <label htmlFor="cnic" className="block mb-2 font-semibold text-gray-700 text-sm">CNIC Number</label>
          <input
            id="cnic"
            type="text"
            placeholder="3310012345678 - 13 digits, no dashes"
            value={form.cnic}
            onChange={setField('cnic')}
            maxLength={13}
            className={`w-full px-4 py-3 border-2 rounded-lg text-base transition-all outline-none
              focus:border-blue-400 focus:ring-2 focus:ring-blue-100
              ${errors.cnic ? 'border-red-400' : 'border-gray-200'}`}
          />
          {errors.cnic && <p className="text-red-500 text-xs mt-1">{errors.cnic}</p>}
          <p className="text-gray-400 text-xs mt-1">Enter 13 digits without dashes.</p>
        </div>

        <button
          type="submit"
          className="w-full py-3 bg-blue-500 hover:bg-blue-600 text-white font-semibold rounded-lg transition-colors"
        >
          Continue
        </button>

        <div className="text-center mt-5 pt-5 border-t border-gray-100">
          <p className="text-sm text-gray-600">
            Already have an account?{' '}
            <Link to="/login" className="text-blue-500 font-semibold hover:underline">Login here</Link>
          </p>
        </div>
      </form>
    </AuthCard>
  )
}
