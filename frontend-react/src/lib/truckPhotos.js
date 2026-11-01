export function getTruckPhotoUrl(truck) {
  const raw = truck?.photo || truck?.truck_photo || truck?.truck_photo_url || truck?.truck_photo_path || ''
  const value = String(raw).trim()

  if (!value) return ''
  if (/^(https?:|data:|blob:)/i.test(value)) return value

  return `/${value.replace(/^\/+/, '')}`
}

export function truckPhotoBackgroundStyle(truck) {
  const photo = getTruckPhotoUrl(truck)

  if (!photo) return undefined

  const safePhoto = photo.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
  return { '--truck-card-photo': `url("${safePhoto}")` }
}

export function hasTruckPhoto(truck) {
  return Boolean(getTruckPhotoUrl(truck))
}