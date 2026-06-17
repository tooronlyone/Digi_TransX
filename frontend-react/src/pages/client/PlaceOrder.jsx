import { Link } from 'react-router-dom'
import { PageTitle, SectionCard } from './clientUtils'

const orderTypes = [
  {
    title: 'One-Time Shipment',
    icon: 'fa-bolt',
    rate: '160 PKR / km',
    description: 'Use this when you need immediate or ad-hoc transport.',
    bullets: ['Fast booking for urgent shipments', 'Single-run route and pricing', 'Flexible truck count and dispatch timing'],
    to: '/client/order/one-time',
    accent: 'bg-blue-50 text-blue-700',
  },
  {
    title: 'Agreement Shipment',
    icon: 'fa-file-signature',
    rate: '145 PKR / km (Save 9%)',
    description: 'Best for recurring operations across fixed routes and schedules.',
    bullets: ['Recurring dispatch schedule', 'Long-term pricing and SLA planning', 'Centralized contract-level visibility'],
    to: '/client/order/agreement',
    accent: 'bg-emerald-50 text-emerald-700',
  },
]

export default function PlaceOrder() {
  return (
    <>
      <PageTitle
        title="Place Order"
        subtitle="Choose order type, fill shipment details, and find available transporters."
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {orderTypes.map((item) => (
          <SectionCard key={item.title} className="h-full">
            <div className="flex h-full flex-col">
              <div className={`grid h-14 w-14 place-items-center rounded-lg ${item.accent}`}>
                <i className={`fas ${item.icon} text-xl`} aria-hidden="true"></i>
              </div>
              <h2 className="mt-5 text-xl font-bold text-slate-900">{item.title}</h2>
              <div className={`mt-3 inline-flex w-fit rounded-full px-3 py-1 text-sm font-bold ${item.accent}`}>
                {item.rate}
              </div>
              <p className="mt-4 text-sm text-slate-600">{item.description}</p>
              <ul className="mt-4 flex-1 space-y-2 text-sm text-slate-600">
                {item.bullets.map((bullet) => (
                  <li key={bullet} className="flex gap-2">
                    <i className="fas fa-check mt-1 text-emerald-600" aria-hidden="true"></i>
                    <span>{bullet}</span>
                  </li>
                ))}
              </ul>
              <Link
                to={item.to}
                className="mt-6 inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
              >
                Open {item.title.split(' ')[0]} Form
                <i className="fas fa-arrow-right" aria-hidden="true"></i>
              </Link>
            </div>
          </SectionCard>
        ))}
      </div>
    </>
  )
}
