import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

async function getCsrf() {
  const cached = sessionStorage.getItem('csrf_token')
  if (cached) return cached
  const res = await fetch('/auth/csrf-token', { credentials: 'include' })
  const data = await res.json()
  const token = data?.csrf_token || ''
  if (token) sessionStorage.setItem('csrf_token', token)
  return token
}

function emptyRow(columns) {
  return Object.fromEntries(columns.map(c => [c.name, '']))
}

export default function TableView() {
  const { tableId } = useParams()
  const navigate = useNavigate()

  const [tableData, setTableData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // editing state: { rowId: number|'new', field: string }
  const [editing, setEditing] = useState(null)
  const [editValue, setEditValue] = useState('')
  const [savingRow, setSavingRow] = useState(null)
  const [deletingRow, setDeletingRow] = useState(null)

  // new row buffer
  const [newRowValues, setNewRowValues] = useState(null)
  const [addingRow, setAddingRow] = useState(false)

  const inputRef = useRef(null)

  function fetchTable() {
    return fetch(`/api/shopkeeper/tables/${tableId}`, { credentials: 'include' })
      .then(r => r.json())
      .then(data => {
        if (data.success) {
          setTableData(data.data)
          if (data.csrf_token) sessionStorage.setItem('csrf_token', data.csrf_token)
        } else {
          setError(data.message || 'Failed to load table.')
        }
      })
      .catch(() => setError('Network error. Please refresh.'))
  }

  useEffect(() => {
    fetchTable().finally(() => setLoading(false))
  }, [tableId])

  useEffect(() => {
    if (editing && inputRef.current) inputRef.current.focus()
  }, [editing])

  function startEdit(rowId, field, currentValue) {
    setEditing({ rowId, field })
    setEditValue(String(currentValue ?? ''))
  }

  async function commitEdit(row) {
    if (!editing) return
    const { rowId, field } = editing
    setEditing(null)

    const newVal = editValue
    const origVal = String(row.values[field] ?? '')
    if (newVal === origVal) return

    setSavingRow(rowId)
    try {
      const csrf = await getCsrf()
      const res = await fetch(`/api/shopkeeper/tables/${tableId}/rows/${rowId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        credentials: 'include',
        body: JSON.stringify({ values: { [field]: newVal } }),
      })
      const data = await res.json()
      if (data.csrf_token) sessionStorage.setItem('csrf_token', data.csrf_token)
      if (data.success) {
        setTableData(prev => ({
          ...prev,
          rows: prev.rows.map(r => r.id === rowId
            ? { ...r, values: { ...r.values, [field]: newVal } }
            : r
          ),
        }))
      }
    } catch (_) {}
    finally { setSavingRow(null) }
  }

  async function deleteRow(rowId) {
    if (!window.confirm('Delete this row?')) return
    setDeletingRow(rowId)
    try {
      const csrf = await getCsrf()
      const res = await fetch(`/api/shopkeeper/tables/${tableId}/rows/${rowId}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        credentials: 'include',
      })
      const data = await res.json()
      if (data.csrf_token) sessionStorage.setItem('csrf_token', data.csrf_token)
      if (data.success) {
        setTableData(prev => ({ ...prev, rows: prev.rows.filter(r => r.id !== rowId) }))
      }
    } catch (_) {}
    finally { setDeletingRow(null) }
  }

  function startAddRow() {
    if (!tableData) return
    setNewRowValues(emptyRow(tableData.columns))
    setAddingRow(false)
  }

  async function submitNewRow() {
    if (!newRowValues || addingRow) return
    setAddingRow(true)
    try {
      const csrf = await getCsrf()
      const res = await fetch(`/api/shopkeeper/tables/${tableId}/rows`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        credentials: 'include',
        body: JSON.stringify({ values: newRowValues }),
      })
      const data = await res.json()
      if (data.csrf_token) sessionStorage.setItem('csrf_token', data.csrf_token)
      if (data.success) {
        const newRow = { id: data.data.row_id, values: { ...newRowValues }, created_at: new Date().toISOString() }
        setTableData(prev => ({ ...prev, rows: [...prev.rows, newRow] }))
        setNewRowValues(null)
      }
    } catch (_) {}
    finally { setAddingRow(false) }
  }

  function renderCell(row, col) {
    const isEditing = editing?.rowId === row.id && editing?.field === col.name
    const isSaving  = savingRow === row.id

    if (isEditing) {
      if (col.type === 'dropdown' && col.options?.length > 0) {
        return (
          <select
            ref={inputRef}
            value={editValue}
            onChange={e => setEditValue(e.target.value)}
            onBlur={() => commitEdit(row)}
            className="w-full px-2 py-1 border border-orange-400 rounded text-sm outline-none bg-white">
            <option value="">—</option>
            {col.options.map(opt => <option key={opt} value={opt}>{opt}</option>)}
          </select>
        )
      }
      return (
        <input
          ref={inputRef}
          type={col.type === 'number' ? 'number' : col.type === 'date' ? 'date' : 'text'}
          value={editValue}
          onChange={e => setEditValue(e.target.value)}
          onBlur={() => commitEdit(row)}
          onKeyDown={e => { if (e.key === 'Enter') commitEdit(row); if (e.key === 'Escape') setEditing(null) }}
          className="w-full px-2 py-1 border border-orange-400 rounded text-sm outline-none bg-white"
        />
      )
    }

    const val = row.values[col.name] ?? ''
    return (
      <div
        onClick={() => !isSaving && startEdit(row.id, col.name, val)}
        className={`min-h-[28px] px-1 rounded cursor-pointer hover:bg-orange-50 transition-colors text-sm text-gray-700
          ${isSaving ? 'opacity-50 cursor-wait' : ''}`}
        title="Click to edit">
        {val !== '' && val !== null && val !== undefined ? String(val) : <span className="text-gray-300">—</span>}
      </div>
    )
  }

  if (loading) return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="w-8 h-8 border-4 border-orange-500 border-t-transparent rounded-full animate-spin" />
    </div>
  )

  if (error) return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="text-center">
        <p className="text-red-600 font-semibold">{error}</p>
        <button onClick={() => navigate('/shopkeeper/dashboard')}
          className="mt-4 text-sm text-blue-500 hover:underline">← Back to Dashboard</button>
      </div>
    </div>
  )

  const { columns = [], rows = [], name = '' } = tableData || {}

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/shopkeeper/dashboard')}
            className="text-gray-400 hover:text-gray-700 transition-colors text-sm">
            ← Dashboard
          </button>
          <span className="text-gray-300">|</span>
          <span className="text-sm font-bold text-blue-500">DigiTransX</span>
          <span className="text-gray-300">|</span>
          <span className="text-sm font-semibold text-orange-600 truncate max-w-[160px]">{name}</span>
        </div>
        <button
          onClick={() => navigate(`/shopkeeper/table/${tableId}/analysis`)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-500 hover:bg-blue-600 text-white text-xs font-semibold rounded-lg transition-colors">
          📈 Analysis
        </button>
      </header>

      <main className="max-w-full px-4 py-6">
        {/* Stats bar */}
        <div className="flex items-center gap-4 mb-4">
          <h1 className="text-xl font-bold text-gray-800">{name}</h1>
          <span className="text-sm text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full">
            {rows.length} row{rows.length !== 1 ? 's' : ''}
          </span>
          <span className="text-sm text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full">
            {columns.length} column{columns.length !== 1 ? 's' : ''}
          </span>
        </div>

        <p className="text-xs text-gray-400 mb-4">
          Click any cell to edit it. Press Enter or click away to save.
        </p>

        {/* Table */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 w-10">#</th>
                {columns.map(col => (
                  <th key={col.name} className="px-3 py-2.5 text-left text-xs font-semibold text-gray-700 whitespace-nowrap">
                    {col.name}
                    <span className="ml-1 text-gray-400 font-normal">({col.type})</span>
                  </th>
                ))}
                <th className="px-3 py-2.5 w-10" />
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => (
                <tr key={row.id}
                  className={`border-b border-gray-100 hover:bg-orange-50/30 transition-colors
                    ${deletingRow === row.id ? 'opacity-40' : ''}`}>
                  <td className="px-3 py-2 text-xs text-gray-400">{idx + 1}</td>
                  {columns.map(col => (
                    <td key={col.name} className="px-3 py-2 min-w-[120px] max-w-[240px]">
                      {renderCell(row, col)}
                    </td>
                  ))}
                  <td className="px-3 py-2">
                    <button
                      onClick={() => deleteRow(row.id)}
                      disabled={!!deletingRow}
                      className="text-gray-300 hover:text-red-500 transition-colors text-lg leading-none disabled:cursor-wait"
                      title="Delete row">
                      ×
                    </button>
                  </td>
                </tr>
              ))}

              {/* New row inputs */}
              {newRowValues && (
                <tr className="border-b border-orange-200 bg-orange-50/40">
                  <td className="px-3 py-2 text-xs text-orange-400">new</td>
                  {columns.map(col => (
                    <td key={col.name} className="px-3 py-2 min-w-[120px]">
                      {col.type === 'dropdown' && col.options?.length > 0 ? (
                        <select
                          value={newRowValues[col.name] || ''}
                          onChange={e => setNewRowValues(p => ({ ...p, [col.name]: e.target.value }))}
                          className="w-full px-2 py-1.5 border border-orange-300 rounded text-sm outline-none bg-white focus:border-orange-500">
                          <option value="">—</option>
                          {col.options.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                        </select>
                      ) : (
                        <input
                          type={col.type === 'number' ? 'number' : col.type === 'date' ? 'date' : 'text'}
                          value={newRowValues[col.name] || ''}
                          onChange={e => setNewRowValues(p => ({ ...p, [col.name]: e.target.value }))}
                          placeholder={col.name}
                          className="w-full px-2 py-1.5 border border-orange-300 rounded text-sm outline-none bg-white focus:border-orange-500 focus:ring-1 focus:ring-orange-200"
                        />
                      )}
                    </td>
                  ))}
                  <td className="px-3 py-2">
                    <button onClick={() => setNewRowValues(null)}
                      className="text-gray-400 hover:text-red-500 transition-colors text-lg leading-none">
                      ×
                    </button>
                  </td>
                </tr>
              )}

              {/* Empty state */}
              {rows.length === 0 && !newRowValues && (
                <tr>
                  <td colSpan={columns.length + 2}
                    className="px-4 py-10 text-center text-gray-400 text-sm">
                    No rows yet. Click "Add Row" to get started.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Action bar */}
        <div className="flex items-center gap-3 mt-4">
          {!newRowValues ? (
            <button onClick={startAddRow}
              className="flex items-center gap-2 px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold rounded-lg transition-colors">
              + Add Row
            </button>
          ) : (
            <button onClick={submitNewRow} disabled={addingRow}
              className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white text-sm font-semibold rounded-lg transition-colors">
              {addingRow && <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
              {addingRow ? 'Saving...' : 'Save Row'}
            </button>
          )}
          {newRowValues && (
            <button onClick={() => setNewRowValues(null)}
              className="px-4 py-2 border border-gray-200 text-gray-600 text-sm rounded-lg hover:bg-gray-50 transition-colors">
              Cancel
            </button>
          )}
          <button
            onClick={() => window.open(`/api/shopkeeper/tables/${tableId}/export`, '_blank')}
            className="ml-auto flex items-center gap-1.5 px-4 py-2 border border-gray-200 text-gray-600 text-sm rounded-lg hover:bg-gray-50 transition-colors">
            ↓ Export CSV
          </button>
          <button
            onClick={() => navigate(`/shopkeeper/table/${tableId}/analysis`)}
            className="flex items-center gap-1.5 px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white text-sm font-semibold rounded-lg transition-colors">
            📈 Analysis
          </button>
        </div>
      </main>
    </div>
  )
}
