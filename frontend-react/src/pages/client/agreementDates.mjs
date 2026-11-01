// Calendar dates must not depend on the browser's UTC offset or roll a 31st
// into the following month. This matches the server's agreements.add_months.
function daysInMonth(year, month) {
  if (month === 2) return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0) ? 29 : 28
  return [4, 6, 9, 11].includes(month) ? 30 : 31
}

export function addAgreementMonths(value, months) {
  const match = typeof value === 'string' && /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match || months === '' || months == null) return ''
  const year = Number(match[1]), month = Number(match[2]), day = Number(match[3])
  const count = Number(months)
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > daysInMonth(year, month)
      || !Number.isSafeInteger(count) || count < 1) return ''
  const monthIndex = (year - 1) * 12 + month - 1 + count
  const endYear = Math.floor(monthIndex / 12) + 1
  const endMonth = monthIndex % 12 + 1
  if (endYear > 9999) return ''
  const endDay = Math.min(day, daysInMonth(endYear, endMonth))
  return `${String(endYear).padStart(4, '0')}-${String(endMonth).padStart(2, '0')}-${String(endDay).padStart(2, '0')}`
}

export function todayAgreementDate(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en', {
    timeZone: 'Asia/Karachi', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(now)
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]))
  return `${values.year}-${values.month}-${values.day}`
}
