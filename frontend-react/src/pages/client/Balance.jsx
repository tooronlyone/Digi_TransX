import { useEffect, useState } from 'react'
import {
  PageTitle,
  PrimaryButton,
  SecondaryButton,
  SectionCard,
  StateMessage,
  StatusBadge,
  apiGet,
  apiSend,
  formatDate,
  formatMoney,
} from './clientUtils'

const emptyPaymentForm = {
  order_id: '',
  amount: '',
  method: 'bank_transfer',
}

export default function Balance() {
  const [balance, setBalance] = useState(null)
  const [payments, setPayments] = useState([])
  const [balanceLoading, setBalanceLoading] = useState(true)
  const [paymentsLoading, setPaymentsLoading] = useState(true)
  const [balanceError, setBalanceError] = useState('')
  const [paymentsError, setPaymentsError] = useState('')
  const [paymentModalOpen, setPaymentModalOpen] = useState(false)
  const [paymentForm, setPaymentForm] = useState(emptyPaymentForm)
  const [paymentSaving, setPaymentSaving] = useState(false)
  const [paymentError, setPaymentError] = useState('')

  async function loadBalance() {
    setBalanceLoading(true)
    setBalanceError('')
    try {
      const json = await apiGet('/api/client/balance')
      setBalance(json.balance || json.data?.balance || {})
    } catch (err) {
      setBalanceError(err.message || 'Failed to load balance.')
    } finally {
      setBalanceLoading(false)
    }
  }

  async function loadPayments() {
    setPaymentsLoading(true)
    setPaymentsError('')
    try {
      const json = await apiGet('/api/client/payments')
      setPayments(json.payments || json.data?.payments || [])
    } catch (err) {
      setPaymentsError(err.message || 'Failed to load payments.')
    } finally {
      setPaymentsLoading(false)
    }
  }

  useEffect(() => {
    loadBalance()
    loadPayments()
  }, [])

  async function submitPayment(event) {
    event.preventDefault()
    setPaymentError('')
    if (!paymentForm.order_id.trim()) {
      setPaymentError('Please enter an Order ID.')
      return
    }
    if (!paymentForm.amount || Number(paymentForm.amount) <= 0) {
      setPaymentError('Please enter a valid amount.')
      return
    }

    setPaymentSaving(true)
    try {
      await apiSend('/api/client/payments', {
        order_id: paymentForm.order_id.trim(),
        amount: Number(paymentForm.amount),
        method: paymentForm.method,
      })
      setPaymentModalOpen(false)
      setPaymentForm(emptyPaymentForm)
      await Promise.all([loadBalance(), loadPayments()])
    } catch (err) {
      setPaymentError(err.message || 'Payment failed.')
    } finally {
      setPaymentSaving(false)
    }
  }

  return (
    <>
      <PageTitle title="Balance & Payments" subtitle="Manage your wallet balance and view payment history." />

      <SectionCard
        title="Balance Summary"
        actions={
          <>
            <SecondaryButton type="button" onClick={loadBalance} disabled={balanceLoading}>
              <i className={`fas ${balanceLoading ? 'fa-spinner fa-spin' : 'fa-sync-alt'}`} aria-hidden="true"></i>
              Refresh
            </SecondaryButton>
            <PrimaryButton type="button" onClick={() => setPaymentModalOpen(true)}>
              <i className="fas fa-credit-card" aria-hidden="true"></i>
              Make Payment
            </PrimaryButton>
          </>
        }
      >
        {balanceLoading && <StateMessage type="loading">Loading balance...</StateMessage>}
        {balanceError && <StateMessage type="error">{balanceError}</StateMessage>}
        {!balanceLoading && !balanceError && (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <article className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="grid h-11 w-11 place-items-center rounded-lg bg-blue-50 text-blue-700">
                <i className="fas fa-wallet" aria-hidden="true"></i>
              </div>
              <div className="mt-3 text-sm font-medium text-slate-500">Wallet Balance</div>
              <div className="mt-1 text-2xl font-bold text-slate-900">{formatMoney(balance?.balance ?? 0)}</div>
              <div className="mt-1 text-xs text-slate-500">Available for withdrawals</div>
            </article>
            <article className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="grid h-11 w-11 place-items-center rounded-lg bg-emerald-50 text-emerald-700">
                <i className="fas fa-receipt" aria-hidden="true"></i>
              </div>
              <div className="mt-3 text-sm font-medium text-slate-500">Total Payments</div>
              <div className="mt-1 text-2xl font-bold text-slate-900">{payments.length}</div>
              <div className="mt-1 text-xs text-slate-500">Successful transactions</div>
            </article>
            <article className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="grid h-11 w-11 place-items-center rounded-lg bg-amber-50 text-amber-700">
                <i className="fas fa-clock" aria-hidden="true"></i>
              </div>
              <div className="mt-3 text-sm font-medium text-slate-500">Last Payment</div>
              <div className="mt-1 text-2xl font-bold text-slate-900">{formatDate(payments[0]?.created_at)}</div>
              <div className="mt-1 text-xs text-slate-500">Most recent transaction</div>
            </article>
          </div>
        )}
      </SectionCard>

      <SectionCard
        title="Payment History"
        actions={
          <SecondaryButton type="button" onClick={loadPayments} disabled={paymentsLoading}>
            <i className={`fas ${paymentsLoading ? 'fa-spinner fa-spin' : 'fa-sync-alt'}`} aria-hidden="true"></i>
            Refresh
          </SecondaryButton>
        }
      >
        {paymentsLoading && <StateMessage type="loading">Loading payments...</StateMessage>}
        {paymentsError && <StateMessage type="error">{paymentsError}</StateMessage>}
        {!paymentsLoading && !paymentsError && payments.length === 0 && (
          <StateMessage type="empty">No payments found.</StateMessage>
        )}
        {!paymentsLoading && !paymentsError && payments.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50 text-left text-xs font-bold uppercase tracking-normal text-slate-500">
                <tr>
                  <th className="px-4 py-3">Payment ID</th>
                  <th className="px-4 py-3">Order ID</th>
                  <th className="px-4 py-3">Amount</th>
                  <th className="px-4 py-3">Method</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {payments.map((payment) => (
                  <tr key={payment.payment_id || payment.id}>
                    <td className="whitespace-nowrap px-4 py-3 font-semibold text-slate-900">{payment.payment_id || payment.payment_code || payment.id || '-'}</td>
                    <td className="px-4 py-3 text-slate-600">{payment.order_id || '-'}</td>
                    <td className="px-4 py-3 text-slate-700">{formatMoney(payment.amount)}</td>
                    <td className="px-4 py-3 capitalize text-slate-600">{String(payment.payment_method || payment.method || '-').replace(/_/g, ' ')}</td>
                    <td className="px-4 py-3"><StatusBadge status={payment.status} /></td>
                    <td className="px-4 py-3 text-slate-600">{formatDate(payment.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {paymentModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 px-4" onClick={() => setPaymentModalOpen(false)}>
          <form className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl" onClick={(event) => event.stopPropagation()} onSubmit={submitPayment}>
            <h3 className="text-lg font-bold text-slate-900">Make Payment</h3>
            <div className="mt-4 space-y-4">
              <label className="block">
                <span className="text-sm font-semibold text-slate-700">Order ID</span>
                <input
                  value={paymentForm.order_id}
                  onChange={(event) => setPaymentForm((form) => ({ ...form, order_id: event.target.value }))}
                  className="mt-1 h-10 w-full rounded-lg border border-slate-300 px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                  placeholder="Enter order ID from current orders"
                />
              </label>
              <label className="block">
                <span className="text-sm font-semibold text-slate-700">Amount (PKR)</span>
                <input
                  type="number"
                  min="1"
                  step="0.01"
                  value={paymentForm.amount}
                  onChange={(event) => setPaymentForm((form) => ({ ...form, amount: event.target.value }))}
                  className="mt-1 h-10 w-full rounded-lg border border-slate-300 px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                  placeholder="Enter amount"
                />
              </label>
              <label className="block">
                <span className="text-sm font-semibold text-slate-700">Payment Method</span>
                <select
                  value={paymentForm.method}
                  onChange={(event) => setPaymentForm((form) => ({ ...form, method: event.target.value }))}
                  className="mt-1 h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                >
                  <option value="bank_transfer">Bank Transfer</option>
                  <option value="card">Credit/Debit Card</option>
                  <option value="wallet">Wallet Balance</option>
                  <option value="easypaisa">EasyPaisa</option>
                  <option value="jazzcash">JazzCash</option>
                </select>
              </label>
            </div>
            {paymentError && <div className="mt-3 text-sm text-red-600">{paymentError}</div>}
            <div className="mt-5 flex gap-2">
              <SecondaryButton type="button" onClick={() => setPaymentModalOpen(false)} className="flex-1">
                Cancel
              </SecondaryButton>
              <PrimaryButton type="submit" disabled={paymentSaving} className="flex-1">
                <i className={`fas ${paymentSaving ? 'fa-spinner fa-spin' : 'fa-credit-card'}`} aria-hidden="true"></i>
                Submit
              </PrimaryButton>
            </div>
          </form>
        </div>
      )}
    </>
  )
}
