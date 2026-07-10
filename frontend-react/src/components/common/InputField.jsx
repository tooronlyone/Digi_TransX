export default function InputField({ label, id, error, ...props }) {
  return (
    <div className="auth-form-field mb-5">
      <label htmlFor={id} className="block mb-2 font-semibold text-gray-700 text-sm">
        {label}
      </label>
      <input
        id={id}
        className={`auth-form-input w-full px-4 py-3 border-2 rounded-lg text-base transition-all outline-none
          focus:border-blue-400 focus:ring-2 focus:ring-blue-100
          ${error ? 'border-red-400' : 'border-gray-200'}`}
        {...props}
      />
      {error && <p className="auth-error text-red-500 text-xs mt-1">{error}</p>}
    </div>
  )
}
