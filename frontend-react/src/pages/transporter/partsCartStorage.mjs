export const PARTS_CART_EVENT = 'dtx:parts-cart-updated'
const EMPTY_CART = Object.freeze([])
const snapshots = new Map()

export function partsCartStorageKey(userId) {
  if ((typeof userId !== 'number' && typeof userId !== 'string')
      || !/^[1-9]\d*$/.test(String(userId))
      || (typeof userId === 'number' && !Number.isSafeInteger(userId))) return null
  return `dtx:parts-cart:v2:${String(userId)}`
}

function parseCart(raw) {
  try {
    const saved = JSON.parse(raw || '[]')
    if (!Array.isArray(saved)) return EMPTY_CART
    return saved.filter(item => item && typeof item === 'object'
      && partsCartStorageKey(item.id) && Number.isSafeInteger(item.qty) && item.qty > 0)
  } catch { return EMPTY_CART }
}

export function readPartsCart(storageKey) {
  if (!storageKey) return EMPTY_CART
  const previous = snapshots.get(storageKey)
  if (previous?.memoryOnly) return previous.items
  try {
    const raw = globalThis.localStorage.getItem(storageKey)
    if (previous && previous.raw === raw) return previous.items
    const items = parseCart(raw)
    snapshots.set(storageKey, { raw, items })
    return items
  } catch {
    return previous?.items || EMPTY_CART
  }
}

export function writePartsCart(storageKey, items) {
  if (!storageKey) return EMPTY_CART
  const raw = JSON.stringify(items)
  let memoryOnly = false
  try { globalThis.localStorage.setItem(storageKey, raw) } catch { memoryOnly = true }
  snapshots.set(storageKey, { raw, items, memoryOnly })
  globalThis.window?.dispatchEvent(new CustomEvent(PARTS_CART_EVENT, { detail: { storageKey } }))
  return items
}

export function countPartsCart(userId) {
  return readPartsCart(partsCartStorageKey(userId)).reduce((total, item) => total + item.qty, 0)
}
