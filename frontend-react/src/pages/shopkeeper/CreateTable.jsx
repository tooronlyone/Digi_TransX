import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

const COLUMN_TYPES = [
  { value: 'text',     label: 'Text' },
  { value: 'number',   label: 'Number' },
  { value: 'date',     label: 'Date' },
  { value: 'dropdown', label: 'Dropdown' },
]

function newColumn() {
  return { id: Date.now() + Math.random(), name: '', type: 'text', options: '' }
}

async function getCsrf() {
  const cached = sessionStorage.getItem('csrf_token')
  if (cached) return cached
  const res = await fetch('/auth/csrf-token', { credentials: 'include' })
  const data = await res.json()
  const token = data?.csrf_token || ''
  if (token) sessionStorage.setItem('csrf_token', token)
  return token
}

export default function CreateTable() {
  const navigate = useNavigate()
  const [tableName, setTableName] = useState('')
  const [columns, setColumns] = useState([newColumn()])
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const [apiError, setApiError] = useState('')

  function addColumn() {
    setColumns(prev => [...prev, newColumn()])
  }

  function removeColumn(id) {
    setColumns(prev => prev.filter(c => c.id !== id))
  }

  function updateColumn(id, field, value) {
    setColumns(prev => prev.map(c => c.id === id ? { ...c, [field]: value } : c))
  }

  function validate() {
    const e = {}
    if (!tableName.trim()) e.tableName = 'Table name is required'
    columns.forEach((col, i) => {
      if (!col.name.trim()) e[`col_${i}`] = 'Column name is required'
    })
    return e
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    setErrors({})
    setApiError('')
    setLoading(true)
    try {
      const csrf = await getCsrf()
      const payload = {
        name: tableName.trim(),
        columns: columns.map(c => ({
          name: c.name.trim(),
          type: c.type,
          ...(c.type === 'dropdown' ? { options: c.options } : {}),
        })),
      }
      const res = await fetch('/api/shopkeeper/tables', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        credentials: 'include',
        body: JSON.stringify(payload),
      })
      const data = await res.json()
      if (data.csrf_token) sessionStorage.setItem('csrf_token', data.csrf_token)
      if (res.ok && data.success) {
        navigate(`/shopkeeper/table/${data.data.table_id}`)
      } else {
        setApiError(data.message || 'Failed to create table.')
      }
    } catch (_) {
      setApiError('Network error. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-3">
        <button onClick={() => navigate('/shopkeeper/dashboard')}
          className="text-gray-400 hover:text-gray-700 transition-colors text-sm">
          ← Back
        </button>
        <span className="text-gray-300">|</span>
        <span className="text-sm font-bold text-blue-500">DigiTransX</span>
        <span className="text-gray-300">|</span>
        <span className="text-sm font-semibold text-orange-600">Create Product Table</span>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-8">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="mb-6">
            <h1 className="text-xl font-bold text-gray-800">Create Product Table</h1>
            <p className="text-sm text-gray-500 mt-1">
              Define the table name and its columns. You can add rows after creating it.
            </p>
          </div>

          {apiError && (
            <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              {apiError}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            {/* Table name */}
            <div className="mb-6">
              <label className="block text-sm font-semibold text-gray-700 mb-1.5">
                Table Name <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={tableName}
                onChange={e => setTableName(e.target.value)}
                placeholder="e.g. Mobile Phones, Shoes, Groceries"
                className={`w-full px-4 py-3 border-2 rounded-lg text-sm outline-none transition-all
                  focus:border-orange-400 focus:ring-2 focus:ring-orange-100
                  ${errors.tableName ? 'border-red-400' : 'border-gray-200'}`}
              />
              {errors.tableName && <p className="text-red-500 text-xs mt-1">{errors.tableName}</p>}
            </div>

            {/* Columns */}
            <div className="mb-6">
              <div className="flex items-center justify-between mb-3">
                <label className="text-sm font-semibold text-gray-700">
                  Columns <span className="text-red-500">*</span>
                </label>
                <button type="button" onClick={addColumn}
                  className="text-xs px-3 py-1.5 bg-orange-50 hover:bg-orange-100 text-orange-600 font-medium rounded-lg border border-orange-200 transition-colors">
                  + Add Column
                </button>
              </div>

              <div className="space-y-3">
                {columns.map((col, i) => (
                  <div key={col.id} className="flex gap-2 items-start p-3 bg-gray-50 rounded-lg border border-gray-200">
                    <div className="flex-1 min-w-0">
                      <input
                        type="text"
                        value={col.name}
                        onChange={e => updateColumn(col.id, 'name', e.target.value)}
                        placeholder={`Column ${i + 1} name (e.g. Price)`}
                        className={`w-full px-3 py-2 border-2 rounded-lg text-sm outline-none transition-all
                          focus:border-orange-400 focus:ring-2 focus:ring-orange-100 bg-white
                          ${errors[`col_${i}`] ? 'border-red-400' : 'border-gray-200'}`}
                      />
                      {errors[`col_${i}`] && <p className="text-red-500 text-xs mt-1">{errors[`col_${i}`]}</p>}
                    </div>

                    <select
                      value={col.type}
                      onChange={e => updateColumn(col.id, 'type', e.target.value)}
                      className="px-3 py-2 border-2 border-gray-200 rounded-lg text-sm outline-none focus:border-orange-400 bg-white text-gray-700 shrink-0">
                      {COLUMN_TYPES.map(t => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                      ))}
                    </select>

                    {columns.length > 1 && (
                      <button type="button" onClick={() => removeColumn(col.id)}
                        className="px-2 py-2 text-gray-400 hover:text-red-500 transition-colors shrink-0 text-lg leading-none">
                        ×
                      </button>
                    )}

                    {col.type === 'dropdown' && (
                      <div className="w-full mt-2 col-span-full">
                        <input
                          type="text"
                          value={col.options}
                          onChange={e => updateColumn(col.id, 'options', e.target.value)}
                          placeholder="Options separated by commas: Red, Blue, Green"
                          className="w-full px-3 py-2 border-2 border-gray-200 rounded-lg text-sm outline-none focus:border-orange-400 focus:ring-2 focus:ring-orange-100 bg-white"
                        />
                        <p className="text-xs text-gray-400 mt-1">Enter options separated by commas</p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Column type legend */}
            <div className="mb-6 p-3 bg-blue-50 rounded-lg border border-blue-100">
              <p className="text-xs text-blue-700 font-medium mb-1">Column types:</p>
              <div className="flex flex-wrap gap-3 text-xs text-blue-600">
                <span><strong>Text</strong> — names, descriptions</span>
                <span><strong>Number</strong> — prices, quantities</span>
                <span><strong>Date</strong> — dates, deadlines</span>
                <span><strong>Dropdown</strong> — fixed choices</span>
              </div>
            </div>

            <div className="flex gap-3">
              <button type="button" onClick={() => navigate('/shopkeeper/dashboard')}
                className="flex-1 py-3 border-2 border-gray-200 text-gray-600 font-semibold rounded-lg hover:bg-gray-50 transition-colors text-sm">
                Cancel
              </button>
              <button type="submit" disabled={loading}
                className="flex-1 py-3 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-400 text-white font-semibold rounded-lg transition-colors text-sm flex items-center justify-center gap-2">
                {loading && <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
                {loading ? 'Creating...' : 'Create Table'}
              </button>
            </div>
          </form>
        </div>
      </main>
    </div>
  )
}
