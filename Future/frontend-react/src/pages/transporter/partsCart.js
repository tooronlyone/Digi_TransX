import { useCallback, useSyncExternalStore } from 'react'
import { AUTH_STATUSES, useAuthVerification } from '../../auth/AuthVerificationContext'
import { PARTS_CART_EVENT, partsCartStorageKey, readPartsCart, writePartsCart, countPartsCart } from './partsCartStorage.mjs'

export function usePartsCart() {
  const { user, status } = useAuthVerification()
  const storageKey = status === AUTH_STATUSES.VERIFIED ? partsCartStorageKey(user?.id) : null
  const subscribe = useCallback(listener => {
    const sync = event => { if (event.detail?.storageKey === storageKey) listener() }
    const syncStorage = event => { if (event.key === storageKey || event.key === null) listener() }
    window.addEventListener(PARTS_CART_EVENT, sync)
    window.addEventListener('storage', syncStorage)
    return () => {
      window.removeEventListener(PARTS_CART_EVENT, sync)
      window.removeEventListener('storage', syncStorage)
    }
  }, [storageKey])
  const snapshot = useCallback(() => readPartsCart(storageKey), [storageKey])
  const cart = useSyncExternalStore(subscribe, snapshot, snapshot)

  // A late callback for account A can update A's cart, never B's current cart.
  const update = useCallback(recipe => writePartsCart(storageKey, recipe(readPartsCart(storageKey))), [storageKey])
  const addItem = useCallback(part => update(current => {
    if (!partsCartStorageKey(part?.id)) return current
    const found = current.find(item => String(item.id) === String(part.id))
    return found
      ? current.map(item => String(item.id) === String(part.id) ? { ...item, qty: item.qty + 1 } : item)
      : [...current, { ...part, qty: 1 }]
  }), [update])
  const changeQty = useCallback((id, delta) => update(current => current
    .map(item => String(item.id) === String(id) ? { ...item, qty: item.qty + delta } : item)
    .filter(item => Number.isSafeInteger(item.qty) && item.qty > 0)), [update])
  const removeItem = useCallback(id => update(current => current.filter(item => String(item.id) !== String(id))), [update])
  const clearCart = useCallback(() => update(() => []), [update])
  return { cart, addItem, changeQty, removeItem, clearCart }
}

// Callers outside React supply their authoritative user ID explicitly.
// Never read the unowned legacy v1 browser cart.
export const getPartsCartCount = countPartsCart
