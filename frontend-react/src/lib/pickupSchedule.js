export const LEAD_MINUTES = 20
const MINUTE = 60 * 1000
const DAY = 24 * 60 * MINUTE

function pakistanParts(timestamp) {
  const date = new Date(timestamp + 5 * 60 * MINUTE).toISOString()
  return { date: date.slice(0, 10), time: date.slice(11, 16) }
}

export function pickupBounds(now = Date.now()) {
  return {
    earliest: pakistanParts(Math.ceil((now + LEAD_MINUTES * MINUTE) / MINUTE) * MINUTE),
    latest: pakistanParts(now + DAY),
  }
}

export function pickupScheduleError(date, time, now = Date.now()) {
  const chosen = Date.parse(`${date}T${time}+05:00`)
  if (!Number.isFinite(chosen)) return 'Please choose a valid pickup date and time.'
  if (chosen < now + LEAD_MINUTES * MINUTE) {
    return `Pickup must be at least ${LEAD_MINUTES} minutes from now so the transporter has time to prepare.`
  }
  if (chosen > now + DAY) return 'Pickup must be within the next 24 hours (Pakistan time).'
  return ''
}
