import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  PageTitle,
  PrimaryButton,
  SecondaryButton,
  SectionCard,
  StateMessage,
  apiSend,
} from './clientUtils'

const transportOptions = [
  ['freight', 'Freight Truck'],
  ['container', 'Container Truck'],
  ['pickup', 'Pickup Truck'],
  ['trailer', 'Trailer'],
  ['refrigerated', 'Refrigerated Truck'],
  ['tanker', 'Tanker Truck'],
  ['express', 'Express Delivery Van'],
]

const emptyTruck = { pickup: '', drop: '', alternate: '' }

function tomorrowIso() {
  const date = new Date()
  date.setDate(date.getDate() + 1)
  return date.toISOString().slice(0, 10)
}

function calculateEndDate(startDate, unit, value) {
  if (!startDate) return ''
  const date = new Date(startDate)
  const amount = Math.max(Number(value || 1), 1)
  if (unit === 'weeks') date.setDate(date.getDate() + amount * 7)
  else if (unit === 'years') date.setFullYear(date.getFullYear() + amount)
  else date.setMonth(date.getMonth() + amount)
  return date.toISOString().slice(0, 10)
}

function scheduleTitle(startDate, index) {
  if (!startDate) return `Day ${index + 1}`
  const date = new Date(startDate)
  date.setDate(date.getDate() + index)
  return date.toLocaleDateString('en-PK', { weekday: 'long', day: 'numeric', month: 'short' })
}

export default function AgreementOrder() {
  const navigate = useNavigate()
  const [transportType, setTransportType] = useState('')
  const [truckCount, setTruckCount] = useState(1)
  const [goodsDescription, setGoodsDescription] = useState('')
  const [durationUnit, setDurationUnit] = useState('months')
  const [durationValue, setDurationValue] = useState(3)
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [trucks, setTrucks] = useState([{ ...emptyTruck }])
  const [scheduleDays, setScheduleDays] = useState(() => Array.from({ length: 7 }, () => ({ expanded: false, schedules: [] })))
  const [agreeTerms, setAgreeTerms] = useState(false)
  const [state, setState] = useState({ type: 'info', message: 'Fill the agreement details to create a draft.' })
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    setEndDate(calculateEndDate(startDate, durationUnit, durationValue))
  }, [startDate, durationUnit, durationValue])

  const minStartDate = useMemo(() => tomorrowIso(), [])

  function setTruckCountClamped(value) {
    const count = Math.min(10, Math.max(1, Number(value || 1)))
    setTruckCount(count)
    setTrucks((current) => {
      const next = current.slice(0, count)
      while (next.length < count) next.push({ ...emptyTruck })
      return next
    })
  }

  function updateTruck(index, field, value) {
    setTrucks((current) => current.map((truck, truckIndex) => (
      truckIndex === index ? { ...truck, [field]: value } : truck
    )))
  }

  function addTruck() {
    setTruckCountClamped(truckCount + 1)
  }

  function removeTruck(index) {
    if (truckCount <= 1) return
    setTrucks((current) => current.filter((_, truckIndex) => truckIndex !== index))
    setTruckCount((count) => Math.max(count - 1, 1))
  }

  function toggleDay(index) {
    setScheduleDays((days) => days.map((day, dayIndex) => (
      dayIndex === index ? { ...day, expanded: !day.expanded } : day
    )))
  }

  function addSchedule(index) {
    setScheduleDays((days) => days.map((day, dayIndex) => {
      if (dayIndex !== index) return day
      return {
        ...day,
        expanded: true,
        schedules: [
          ...day.schedules,
          {
            id: `${Date.now()}-${day.schedules.length}`,
            truck: '1',
            pickupTime: '',
            location: '',
            durationHours: 8,
            instructions: '',
          },
        ],
      }
    }))
  }

  function updateSchedule(dayIndex, scheduleId, field, value) {
    setScheduleDays((days) => days.map((day, index) => {
      if (index !== dayIndex) return day
      return {
        ...day,
        schedules: day.schedules.map((schedule) => (
          schedule.id === scheduleId ? { ...schedule, [field]: value } : schedule
        )),
      }
    }))
  }

  function removeSchedule(dayIndex, scheduleId) {
    setScheduleDays((days) => days.map((day, index) => (
      index === dayIndex
        ? { ...day, schedules: day.schedules.filter((schedule) => schedule.id !== scheduleId) }
        : day
    )))
  }

  function resetForm() {
    if (!window.confirm('Are you sure you want to reset the form? All entered data will be lost.')) return
    setTransportType('')
    setTruckCount(1)
    setGoodsDescription('')
    setDurationUnit('months')
    setDurationValue(3)
    setStartDate('')
    setEndDate('')
    setTrucks([{ ...emptyTruck }])
    setScheduleDays(Array.from({ length: 7 }, () => ({ expanded: false, schedules: [] })))
    setAgreeTerms(false)
    setState({ type: 'info', message: 'Fill the agreement details to create a draft.' })
  }

  async function submitAgreement() {
    const pickup = trucks[0]?.pickup.trim() || ''
    const drop = trucks[0]?.drop.trim() || ''
    if (!transportType) {
      setState({ type: 'error', message: 'Please select a transport type.' })
      return
    }
    if (!goodsDescription.trim()) {
      setState({ type: 'error', message: 'Please provide the goods description.' })
      return
    }
    if (!startDate) {
      setState({ type: 'error', message: 'Please select an agreement start date.' })
      return
    }
    if (!pickup || !drop) {
      setState({ type: 'error', message: 'Primary pickup and drop-off locations are required.' })
      return
    }
    if (!agreeTerms) {
      setState({ type: 'error', message: 'You must agree to the terms and conditions.' })
      return
    }

    setSubmitting(true)
    setState({ type: 'loading', message: 'Creating agreement draft...' })
    try {
      const json = await apiSend('/api/agreements', {
        truck_type: transportType,
        truck_count: truckCount,
        goods_type: goodsDescription.trim(),
        pickup_location: pickup,
        dropoff_location: drop,
        same_locations: Boolean(pickup && drop),
        start_date: startDate,
        end_date: endDate || '',
        estimated_trip_count: Number(durationValue || 0),
        buffer_margin: 0.05,
      })
      const agreement = json.agreement || {}
      setState({ type: 'success', message: `Agreement draft created successfully. ID: ${agreement.display_id || ''}` })
      setTimeout(() => navigate('/client/agreements'), 700)
    } catch (err) {
      setState({ type: 'error', message: err.message || 'Failed to create agreement.' })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <PageTitle
        title="Agreement Order"
        subtitle="Set up a long-term transportation agreement with scheduled deliveries."
        actions={
          <Link to="/client/place-order" className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
            <i className="fas fa-arrow-left" aria-hidden="true"></i>
            Back to Order Types
          </Link>
        }
      />

      <StateMessage type="info" title="Important">
        You must schedule each day's requirements at least 24 hours in advance. For urgent same-day requirements, schedule at least 30 minutes before the required time.
      </StateMessage>

      <SectionCard title="Agreement Details" icon="fa-file-contract">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <label className="block">
            <span className="text-sm font-semibold text-slate-700">Transport Type</span>
            <select value={transportType} onChange={(event) => setTransportType(event.target.value)} className="mt-1 h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100">
              <option value="">Select Transport Type</option>
              {transportOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="text-sm font-semibold text-slate-700">Number of Trucks</span>
            <input type="number" min="1" max="10" value={truckCount} onChange={(event) => setTruckCountClamped(event.target.value)} className="mt-1 h-10 w-full rounded-lg border border-slate-300 px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" />
          </label>
          <label className="block md:col-span-2">
            <span className="text-sm font-semibold text-slate-700">Actual Goods Description</span>
            <textarea value={goodsDescription} onChange={(event) => setGoodsDescription(event.target.value)} rows={3} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" placeholder="Describe the goods being transported daily or regularly" />
          </label>
          <label className="block">
            <span className="text-sm font-semibold text-slate-700">Agreement Duration</span>
            <div className="mt-1 grid grid-cols-[1fr_90px] gap-2">
              <select value={durationUnit} onChange={(event) => setDurationUnit(event.target.value)} className="h-10 rounded-lg border border-slate-300 bg-white px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100">
                <option value="weeks">Weeks</option>
                <option value="months">Months</option>
                <option value="years">Years</option>
              </select>
              <input type="number" min="1" max="60" value={durationValue} onChange={(event) => setDurationValue(event.target.value)} className="h-10 rounded-lg border border-slate-300 px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" />
            </div>
          </label>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">Start Date</span>
              <input type="date" min={minStartDate} value={startDate} onChange={(event) => setStartDate(event.target.value)} className="mt-1 h-10 w-full rounded-lg border border-slate-300 px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" />
            </label>
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">End Date</span>
              <input type="date" value={endDate} readOnly className="mt-1 h-10 w-full rounded-lg border border-slate-200 bg-slate-100 px-3 text-sm text-slate-600" />
            </label>
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="Truck & Location Details"
        icon="fa-truck"
        actions={<SecondaryButton type="button" onClick={addTruck}><i className="fas fa-plus-circle" aria-hidden="true"></i> Add Another Truck</SecondaryButton>}
      >
        <div className="space-y-4">
          {trucks.map((truck, index) => (
            <div key={index} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <h3 className="font-semibold text-slate-900">Truck #{index + 1} Details</h3>
                {trucks.length > 1 && (
                  <button type="button" onClick={() => removeTruck(index)} className="text-sm font-semibold text-red-600 hover:text-red-700">
                    <i className="fas fa-times mr-1" aria-hidden="true"></i> Remove Truck
                  </button>
                )}
              </div>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <label className="block">
                  <span className="text-sm font-semibold text-slate-700">Primary Pickup Location</span>
                  <input value={truck.pickup} onChange={(event) => updateTruck(index, 'pickup', event.target.value)} className="mt-1 h-10 w-full rounded-lg border border-slate-300 px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" placeholder="Main pickup address" />
                </label>
                <label className="block">
                  <span className="text-sm font-semibold text-slate-700">Primary Drop-off Location</span>
                  <input value={truck.drop} onChange={(event) => updateTruck(index, 'drop', event.target.value)} className="mt-1 h-10 w-full rounded-lg border border-slate-300 px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" placeholder="Main drop-off address" />
                </label>
                <label className="block md:col-span-2">
                  <span className="text-sm font-semibold text-slate-700">Alternate Locations</span>
                  <textarea value={truck.alternate} onChange={(event) => updateTruck(index, 'alternate', event.target.value)} rows={2} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" placeholder="Any alternate pickup/drop locations that might be used occasionally" />
                </label>
              </div>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="Daily Schedule Setup" icon="fa-calendar-alt">
        <StateMessage type="info" title="Scheduling Rules">
          Schedule must be set at least 24 hours in advance. Days without schedule will not have trucks dispatched.
        </StateMessage>
        <div className="mt-4 space-y-3">
          {scheduleDays.map((day, dayIndex) => (
            <div key={dayIndex} className="rounded-lg border border-slate-200">
              <button type="button" onClick={() => toggleDay(dayIndex)} className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left font-semibold text-slate-900">
                <span><i className="fas fa-calendar-day mr-2 text-blue-600" aria-hidden="true"></i>{scheduleTitle(startDate, dayIndex)}</span>
                <i className={`fas fa-chevron-${day.expanded ? 'up' : 'down'} text-slate-500`} aria-hidden="true"></i>
              </button>
              {day.expanded && (
                <div className="space-y-3 border-t border-slate-200 p-4">
                  {day.schedules.length === 0 && (
                    <StateMessage type="empty">No trucks scheduled for this day. Add a schedule to set requirements.</StateMessage>
                  )}
                  {day.schedules.map((schedule) => (
                    <div key={schedule.id} className="rounded-lg bg-slate-50 p-4">
                      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                        <label className="block">
                          <span className="text-sm font-semibold text-slate-700">Truck Required</span>
                          <select value={schedule.truck} onChange={(event) => updateSchedule(dayIndex, schedule.id, 'truck', event.target.value)} className="mt-1 h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100">
                            {trucks.map((_, index) => <option key={index + 1} value={String(index + 1)}>Truck #{index + 1}</option>)}
                            <option value="all">All Trucks</option>
                          </select>
                        </label>
                        <label className="block">
                          <span className="text-sm font-semibold text-slate-700">Pickup Time</span>
                          <input type="time" value={schedule.pickupTime} onChange={(event) => updateSchedule(dayIndex, schedule.id, 'pickupTime', event.target.value)} className="mt-1 h-10 w-full rounded-lg border border-slate-300 px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" />
                        </label>
                        <label className="block">
                          <span className="text-sm font-semibold text-slate-700">Location (if different)</span>
                          <input value={schedule.location} onChange={(event) => updateSchedule(dayIndex, schedule.id, 'location', event.target.value)} className="mt-1 h-10 w-full rounded-lg border border-slate-300 px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" placeholder="Optional different pickup location" />
                        </label>
                        <label className="block">
                          <span className="text-sm font-semibold text-slate-700">Duration (hours)</span>
                          <input type="number" min="1" max="24" value={schedule.durationHours} onChange={(event) => updateSchedule(dayIndex, schedule.id, 'durationHours', event.target.value)} className="mt-1 h-10 w-full rounded-lg border border-slate-300 px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" />
                        </label>
                        <label className="block md:col-span-2">
                          <span className="text-sm font-semibold text-slate-700">Special Instructions</span>
                          <textarea value={schedule.instructions} onChange={(event) => updateSchedule(dayIndex, schedule.id, 'instructions', event.target.value)} rows={2} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" placeholder="Any special requirements" />
                        </label>
                      </div>
                      <button type="button" onClick={() => removeSchedule(dayIndex, schedule.id)} className="mt-3 text-sm font-semibold text-red-600 hover:text-red-700">
                        <i className="fas fa-trash mr-1" aria-hidden="true"></i> Remove This Schedule
                      </button>
                    </div>
                  ))}
                  <SecondaryButton type="button" onClick={() => addSchedule(dayIndex)}>
                    <i className="fas fa-plus" aria-hidden="true"></i> Add Schedule
                  </SecondaryButton>
                </div>
              )}
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="Terms & Conditions" icon="fa-gavel">
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
          <ol className="list-decimal space-y-1 pl-5">
            <li>Minimum agreement period: 1 week</li>
            <li>Cancellation requires 7 days notice</li>
            <li>Schedules must be provided 24 hours in advance</li>
            <li>Emergency requests within 30 minutes are subject to surcharge</li>
            <li>Monthly billing is based on actual usage</li>
            <li>Insurance coverage follows the selected plan</li>
          </ol>
        </div>
        <label className="mt-4 flex items-start gap-3 text-sm text-slate-700">
          <input type="checkbox" checked={agreeTerms} onChange={(event) => setAgreeTerms(event.target.checked)} className="mt-1 h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500" />
          <span>I agree to the terms and conditions of this transportation agreement.</span>
        </label>
      </SectionCard>

      <SectionCard>
        <div className="space-y-4">
          <StateMessage type={state.type}>{state.message}</StateMessage>
          <div className="flex flex-wrap justify-end gap-2">
            <SecondaryButton type="button" onClick={resetForm} disabled={submitting}>
              <i className="fas fa-undo-alt" aria-hidden="true"></i> Reset Form
            </SecondaryButton>
            <PrimaryButton type="button" onClick={submitAgreement} disabled={submitting}>
              <i className={`fas ${submitting ? 'fa-spinner fa-spin' : 'fa-file-signature'}`} aria-hidden="true"></i>
              Create Agreement
            </PrimaryButton>
          </div>
        </div>
      </SectionCard>
    </>
  )
}
