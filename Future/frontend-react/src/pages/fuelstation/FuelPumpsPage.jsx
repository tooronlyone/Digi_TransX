import { useEffect, useState } from 'react'
import { useApi } from '../../hooks/useApi'
import FuelStationLayout from '../../components/fuelstation/FuelStationLayout'

const FUEL_OPTIONS = [
  { value: 'diesel', label: 'High Speed Diesel (HSD)' },
  { value: 'petrol', label: 'Super Petrol (Euro 5)' },
  { value: 'hi_octane', label: 'Hi-Octane 97' },
  { value: 'cng', label: 'Compressed Natural Gas (CNG)' },
  { value: 'adblue', label: 'AdBlue / DEF Fluid' },
]

export default function FuelPumpsPage() {
  const api = useApi()
  const [pumps, setPumps] = useState([])
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({})
  const [showAddModal, setShowAddModal] = useState(false)
  const [newPump, setNewPump] = useState({
    pump_number: '',
    fuel_type: 'diesel',
    price_per_liter: '282.50',
    tank_capacity_liters: '25000',
    current_stock_liters: '18000',
  })
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let ignore = false
    api.get('/api/fuelstation/pumps')
      .then(res => {
        if (!ignore && res.success) setPumps(res.pumps || [])
      })
      .catch(() => {
        if (!ignore) setError('Unable to load pumps from server.')
      })
      .finally(() => {
        if (!ignore) setLoading(false)
      })
    return () => { ignore = true }
  }, [api, reloadKey])

  function startEdit(pump) {
    setEditingId(pump.id)
    setEditForm({
      pump_number: pump.pump_number,
      fuel_type: pump.fuel_type,
      price_per_liter: String(pump.price_per_liter),
      status: pump.status,
      current_stock_liters: String(pump.current_stock_liters),
      tank_capacity_liters: String(pump.tank_capacity_liters),
    })
  }

  async function handleSaveEdit(pumpId) {
    setError('')
    try {
      const res = await api.put(`/api/fuelstation/pumps/${pumpId}`, {
        pump_number: editForm.pump_number,
        fuel_type: editForm.fuel_type,
        price_per_liter: parseFloat(editForm.price_per_liter),
        status: editForm.status,
        current_stock_liters: parseFloat(editForm.current_stock_liters),
        tank_capacity_liters: parseFloat(editForm.tank_capacity_liters),
      })
      if (res.success) {
        setNotice('Pump rate & configuration updated successfully.')
        setEditingId(null)
        setReloadKey((k) => k + 1)
      } else {
        setError(res.message || 'Failed to update pump.')
      }
    } catch (err) {
      setError(err.message || 'Failed to save changes.')
    }
  }

  async function handleAddPump(e) {
    e.preventDefault()
    setError('')
    try {
      const res = await api.post('/api/fuelstation/pumps', {
        pump_number: newPump.pump_number,
        fuel_type: newPump.fuel_type,
        price_per_liter: parseFloat(newPump.price_per_liter),
        tank_capacity_liters: parseFloat(newPump.tank_capacity_liters),
        current_stock_liters: parseFloat(newPump.current_stock_liters),
      })
      if (res.success) {
        setNotice('New pump added successfully!')
        setShowAddModal(false)
        setNewPump({ pump_number: '', fuel_type: 'diesel', price_per_liter: '282.50', tank_capacity_liters: '25000', current_stock_liters: '18000' })
        setReloadKey((k) => k + 1)
      } else {
        setError(res.message || 'Failed to add pump.')
      }
    } catch (err) {
      setError(err.message || 'Error creating pump.')
    }
  }

  return (
    <FuelStationLayout>
      {notice && (
        <div style={{ background: '#ecf9f4', border: '1px solid #c4eadc', color: '#176b54', padding: '10px 14px', borderRadius: 8, marginBottom: 16 }}>
          <i className="fa-solid fa-circle-check" style={{ marginRight: 6 }} /> {notice}
        </div>
      )}

      {error && (
        <div style={{ background: '#fff0f0', border: '1px solid #ffcaca', color: '#a93737', padding: '10px 14px', borderRadius: 8, marginBottom: 16 }}>
          <i className="fa-solid fa-circle-exclamation" style={{ marginRight: 6 }} /> {error}
        </div>
      )}

      <div className="fuel-card">
        <div className="fuel-card__header">
          <div>
            <h2>Pumps, Dispensers &amp; Live Fuel Rates</h2>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: '#94a3b8' }}>
              Set PKR rates per liter, view tank stock levels, and toggle pump maintenance status.
            </p>
          </div>
          <button
            className="fuel-btn fuel-btn--primary"
            onClick={() => setShowAddModal(true)}
          >
            <i className="fa-solid fa-plus" /> Add Dispenser Pump
          </button>
        </div>

        <div className="fuel-table-wrapper">
          <table className="fuel-table">
            <thead>
              <tr>
                <th>Bay / Nozzle</th>
                <th>Fuel Grade</th>
                <th>Price per Liter (PKR)</th>
                <th>Current Stock</th>
                <th>Tank Capacity</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {pumps.map(p => {
                const isEditing = editingId === p.id
                return (
                  <tr key={p.id}>
                    <td>
                      {isEditing ? (
                        <input
                          type="text"
                          className="fuel-form-input"
                          style={{ padding: '6px 10px', fontSize: 13 }}
                          value={editForm.pump_number}
                          onChange={e => setEditForm({ ...editForm, pump_number: e.target.value })}
                        />
                      ) : (
                        <strong>{p.pump_number}</strong>
                      )}
                    </td>

                    <td>
                      {isEditing ? (
                        <select
                          className="fuel-form-select"
                          style={{ padding: '6px 10px', fontSize: 13 }}
                          value={editForm.fuel_type}
                          onChange={e => setEditForm({ ...editForm, fuel_type: e.target.value })}
                        >
                          {FUEL_OPTIONS.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                        </select>
                      ) : (
                        p.fuel_type_label
                      )}
                    </td>

                    <td>
                      {isEditing ? (
                        <input
                          type="number"
                          step="0.01"
                          className="fuel-form-input"
                          style={{ padding: '6px 10px', fontSize: 13, width: 120 }}
                          value={editForm.price_per_liter}
                          onChange={e => setEditForm({ ...editForm, price_per_liter: e.target.value })}
                        />
                      ) : (
                        <strong style={{ color: '#22c55e', fontSize: 15 }}>Rs. {p.price_per_liter.toFixed(2)}</strong>
                      )}
                    </td>

                    <td>
                      {isEditing ? (
                        <input
                          type="number"
                          step="100"
                          className="fuel-form-input"
                          style={{ padding: '6px 10px', fontSize: 13, width: 120 }}
                          value={editForm.current_stock_liters}
                          onChange={e => setEditForm({ ...editForm, current_stock_liters: e.target.value })}
                        />
                      ) : (
                        `${p.current_stock_liters.toLocaleString()} Liters`
                      )}
                    </td>

                    <td>{p.tank_capacity_liters.toLocaleString()} Liters</td>

                    <td>
                      {isEditing ? (
                        <select
                          className="fuel-form-select"
                          style={{ padding: '6px 10px', fontSize: 13 }}
                          value={editForm.status}
                          onChange={e => setEditForm({ ...editForm, status: e.target.value })}
                        >
                          <option value="active">Active</option>
                          <option value="maintenance">Maintenance</option>
                          <option value="inactive">Inactive</option>
                        </select>
                      ) : (
                        <span className={`fuel-badge fuel-badge--${p.status}`}>{p.status}</span>
                      )}
                    </td>

                    <td>
                      {isEditing ? (
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button
                            className="fuel-btn fuel-btn--success"
                            style={{ padding: '6px 12px', fontSize: 12 }}
                            onClick={() => handleSaveEdit(p.id)}
                          >
                            Save
                          </button>
                          <button
                            className="fuel-btn"
                            style={{ padding: '6px 12px', fontSize: 12, background: '#475569', color: '#fff' }}
                            onClick={() => setEditingId(null)}
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button
                          className="fuel-btn"
                          style={{ padding: '6px 12px', fontSize: 12, background: '#334155', color: '#f59e0b' }}
                          onClick={() => startEdit(p)}
                        >
                          <i className="fa-solid fa-pen-to-square" /> Edit Rate
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
              {pumps.length === 0 && !loading && (
                <tr>
                  <td colSpan="7" style={{ textAlign: 'center', padding: '32px', color: '#94a3b8' }}>
                    No pumps configured yet. Click "Add Dispenser Pump" above to set up your bays.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add Pump Modal */}
      {showAddModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,35,55,0.45)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ background: '#ffffff', border: '1px solid #dfe7f0', boxShadow: '0 24px 60px rgba(15,35,55,.2)', borderRadius: 14, padding: 28, width: 440, maxWidth: '90%' }}>
            <h3 style={{ margin: '0 0 16px', color: '#102a43' }}>Add New Dispenser Pump</h3>
            <form onSubmit={handleAddPump}>
              <div className="fuel-form-group">
                <label>Pump / Bay Name *</label>
                <input
                  type="text"
                  placeholder="e.g. Bay 5 - Heavy Diesel"
                  className="fuel-form-input"
                  value={newPump.pump_number}
                  onChange={e => setNewPump({ ...newPump, pump_number: e.target.value })}
                  required
                />
              </div>

              <div className="fuel-form-group">
                <label>Fuel Type *</label>
                <select
                  className="fuel-form-select"
                  value={newPump.fuel_type}
                  onChange={e => setNewPump({ ...newPump, fuel_type: e.target.value })}
                >
                  {FUEL_OPTIONS.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                </select>
              </div>

              <div className="fuel-form-group">
                <label>Price per Liter (PKR) *</label>
                <input
                  type="number"
                  step="0.01"
                  className="fuel-form-input"
                  value={newPump.price_per_liter}
                  onChange={e => setNewPump({ ...newPump, price_per_liter: e.target.value })}
                  required
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div className="fuel-form-group">
                  <label>Tank Capacity (L)</label>
                  <input
                    type="number"
                    className="fuel-form-input"
                    value={newPump.tank_capacity_liters}
                    onChange={e => setNewPump({ ...newPump, tank_capacity_liters: e.target.value })}
                  />
                </div>
                <div className="fuel-form-group">
                  <label>Current Stock (L)</label>
                  <input
                    type="number"
                    className="fuel-form-input"
                    value={newPump.current_stock_liters}
                    onChange={e => setNewPump({ ...newPump, current_stock_liters: e.target.value })}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
                <button type="submit" className="fuel-btn fuel-btn--primary" style={{ flex: 1 }}>
                  Create Pump
                </button>
                <button
                  type="button"
                  className="fuel-btn"
                  style={{ background: '#eef2f6', color: '#40566d', border: '1px solid #d9e2ec' }}
                  onClick={() => setShowAddModal(false)}
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </FuelStationLayout>
  )
}
