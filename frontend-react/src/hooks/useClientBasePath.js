import { useLocation } from 'react-router-dom'

/*
 * The one-time order pages (PostOrder, MyOrders, ClientOrderDetail, BidCheckout,
 * Terms) are shared by BOTH the business client surface (/client/*) and the
 * everyday surface (/everyday/*). This hook returns the base path for the
 * surface the page is currently rendered under, so a single component can build
 * correct links/redirects for either — no duplicated pages.
 */
export default function useClientBasePath() {
  const { pathname } = useLocation()
  return pathname.startsWith('/everyday') ? '/everyday' : '/client'
}
