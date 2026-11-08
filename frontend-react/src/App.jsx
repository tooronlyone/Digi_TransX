import React from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import ActivityTracker from './components/ActivityTracker'
import GenuineActivity from './components/GenuineActivity'
import AccessLockProvider from './components/security/AccessLockProvider'
import { StepUpProvider } from './components/security/StepUpProvider'
import SignupWizardProvider, { RequireSignupBasic, RequireSignupDraft } from './components/auth/SignupWizardProvider'

import Login from './pages/auth/Login'
import Signup from './pages/auth/Signup'
import SignupTerms from './pages/auth/SignupTerms'
import InsuranceReminder from './components/common/InsuranceReminder'
import RoleSelect from './pages/auth/RoleSelect'
import ResetPassword from './pages/auth/ResetPassword'
import MainPage from './pages/main/MainPage'

import ServiceSeekerDetails from './pages/auth/roledetails/ServiceSeekerDetails'
import LogisticsProviderDetails from './pages/auth/roledetails/LogisticsProviderDetails'
import EverydayUserDetails from './pages/auth/roledetails/EverydayUserDetails'
import DriverDetails from './pages/auth/roledetails/DriverDetails'
import DriverGuard from './components/driver/DriverGuard'
import DriverLayout from './components/driver/DriverLayout'
import DriverDashboard from './pages/driver/DriverDashboard'
import DriverActiveTrip from './pages/driver/DriverActiveTrip'
import DriverTrips from './pages/driver/DriverTrips'
import DriverWallet from './pages/driver/DriverWallet'
import DriverReputation from './pages/driver/DriverReputation'
import DriverProfile from './pages/driver/DriverProfile'
import DriverFuelLogs from './pages/driver/DriverFuelLogs'

import TransporterGuard from './components/transporter/TransporterGuard'
import TransporterLayout from './components/transporter/TransporterLayout'
import TransporterPlaceholderPage from './components/transporter/TransporterPlaceholderPage'
import ClientLayout from './components/client/ClientLayout'
import useClientAuth from './hooks/useClientAuth'
import EverydayGuard from './components/everyday/EverydayGuard'
import EverydayLayout from './components/everyday/EverydayLayout'
import EverydayDashboard from './pages/everyday/EverydayDashboard'

import Dashboard from './pages/transporter/transporter_dashboard'
import MyTrucks from './pages/transporter/My Truck'
import AddTruck from './pages/transporter/add_truck'
import TruckDetails from './pages/transporter/truck_details'
import EditTruck from './pages/transporter/edit_truck'
import TruckConfiguration from './pages/transporter/truck_configuration'
import TrackTruck from './pages/transporter/track_truck'
// import ServiceHistory from './pages/future/service_history'
import AvailableBids from './pages/transporter/AvailableBids'
import MyBids from './pages/transporter/MyBids'
import OrderTracking from './pages/transporter/OrderTracking'
import TransporterAgreementBids from './pages/transporter/AgreementBids'
import TransporterMyAgreements from './pages/transporter/MyAgreements'
import Earnings from './pages/transporter/earning'
import TransporterWallet from './pages/transporter/wallet'
import AccountHistory from './pages/transporter/ac_history'
import Profile from './pages/transporter/profile'
import Settings from './pages/transporter/settings'
import Leaderboard from './pages/transporter/leaderboard'
import Help from './pages/transporter/help'
import About from './pages/transporter/about'
import Contact from './pages/transporter/contact'
import Terms from './pages/transporter/terms'
import Privacy from './pages/transporter/privacy'
import OrgUnavailablePage from './components/org/OrgUnavailablePage'
import ClientDashboard from './pages/client/ClientDashboard'
import PostOrder from './pages/client/PostOrder'
import MyOrders from './pages/client/MyOrders'
import ClientOrderDetail from './pages/client/ClientOrderDetail'
import BidCheckout from './pages/client/BidCheckout'
import Agreements from './pages/client/Agreements'
import PostAgreement from './pages/client/PostAgreement'
import ClientAgreementBids from './pages/client/AgreementBids'
import ClientMyAgreements from './pages/client/MyAgreements'
import AgreementDetail from './pages/client/AgreementDetail'
import Wallet from './pages/client/Wallet'
import ClientAccount from './pages/client/ClientAccount'
import ClientMessages from './pages/client/Messages'
import TransporterMessages from './pages/transporter/Messages'
import AdminLayout from './components/admin/AdminLayout'
import AdminLogin from './pages/admin/AdminLogin'
import AdminDashboard from './pages/admin/AdminDashboard'
import AdminUsers from './pages/admin/AdminUsers'
import AdminUserDetail from './pages/admin/AdminUserDetail'
import AdminTrucks from './pages/admin/AdminTrucks'
import AdminWithdrawals from './pages/admin/AdminWithdrawals'
import AdminAgreements from './pages/admin/AdminAgreements'
import AdminDisputes from './pages/admin/AdminDisputes'
import AdminDisputeChat from './pages/admin/AdminDisputeChat'
import AdminPayments from './pages/admin/AdminPayments'
import AdminPlatformSettings from './pages/admin/AdminPlatformSettings'
import ClientTerms from './pages/client/Terms'
import SecuritySettings from './pages/shared/SecuritySettings'
import { AUTH_STATUSES, useAuthVerification } from './auth/AuthVerificationContext'

function ClientGuard({ children }) {
  const { ready } = useClientAuth()

  if (!ready) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-slate-50">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
        <p className="text-sm text-slate-500">Checking session...</p>
      </div>
    )
  }
  return children
}

function AdminGuard({ children }) {
  const { status, user } = useAuthVerification()

  if (status === AUTH_STATUSES.CHECKING || status === AUTH_STATUSES.PRESENTED) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-cyan-500 border-t-transparent" />
      </div>
    )
  }

  if (status === AUTH_STATUSES.UNAUTHORIZED || (status === AUTH_STATUSES.VERIFIED && user?.role !== 'platform_admin')) {
    return <Navigate to="/admin/login" replace />
  }

  return children
}

function UnlockRoute() {
  const { status, user } = useAuthVerification()
  if (status === AUTH_STATUSES.UNAUTHORIZED) return <Navigate to="/login" replace />
  if (status === AUTH_STATUSES.VERIFIED) {
    const role = String(user?.role || '').trim().toLowerCase()
    const destination = role === 'everyday_user'
      ? '/everyday/dashboard'
      : role === 'client' || role === 'service_seeker'
        ? '/client/dashboard'
        : role === 'driver'
              ? '/driver/dashboard'
              : role === 'transporter' || role === 'logistics_provider'
            ? '/transporter/dashboard'
            : '/main'
    return <Navigate to={destination} replace />
  }
  return <div className="shell-page-skeleton" aria-busy="true" />
}

function AdminPortal() {
  return (
    <AdminGuard>
      <AdminLayout>
        <Routes>
          <Route path="dashboard" element={<AdminDashboard />} />
          <Route path="users" element={<AdminUsers />} />
          <Route path="users/:id" element={<AdminUserDetail />} />
          <Route path="trucks" element={<AdminTrucks />} />
          <Route path="withdrawals" element={<AdminWithdrawals />} />
          <Route path="agreements" element={<AdminAgreements />} />
          <Route path="disputes" element={<AdminDisputes />} />
          <Route path="dispute-chat/:threadId" element={<AdminDisputeChat />} />
          <Route path="payments" element={<AdminPayments />} />
          <Route path="platform-settings" element={<AdminPlatformSettings />} />
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="*" element={<Navigate to="dashboard" replace />} />
        </Routes>
      </AdminLayout>
    </AdminGuard>
  )
}

function ClientPortal() {
  return (
    <ClientGuard>
      <ClientLayout>
        <Routes>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<ClientDashboard />} />
          <Route path="post-order" element={<PostOrder />} />
          <Route path="orders" element={<MyOrders />} />
          <Route path="order/:orderId" element={<ClientOrderDetail />} />
          <Route path="order/:orderId/bid/:bidId/checkout" element={<BidCheckout />} />
          <Route path="agreements" element={<Navigate to="/client/my-agreements" replace />} />
          <Route path="post-agreement" element={<PostAgreement />} />
          <Route path="agreement-bids/:postId" element={<ClientAgreementBids />} />
          <Route path="my-agreements" element={<ClientMyAgreements />} />
          <Route path="agreement/:id" element={<AgreementDetail />} />
          <Route path="wallet" element={<Wallet />} />
          <Route path="balance" element={<Wallet />} />
          <Route path="account" element={<ClientAccount />} />
          <Route path="security" element={<SecuritySettings />} />
          <Route path="messages" element={<ClientMessages />} />
          <Route path="terms" element={<ClientTerms />} />
          <Route path="*" element={<Navigate to="/client/dashboard" replace />} />
        </Routes>
      </ClientLayout>
    </ClientGuard>
  )
}

function EverydayPortal() {
  // Everyday users reuse the SAME order pages as business clients (PostOrder,
  // MyOrders, ClientOrderDetail, BidCheckout, ClientTerms) — they build correct
  // /everyday/* links via useClientBasePath. No wallet/agreement routes exist
  // here, and an everyday user hitting an unknown path returns to their surface.
  return (
    <EverydayGuard>
      <EverydayLayout>
        <Routes>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<EverydayDashboard />} />
          <Route path="post-order" element={<PostOrder />} />
          <Route path="orders" element={<MyOrders />} />
          <Route path="order/:orderId" element={<ClientOrderDetail />} />
          <Route path="order/:orderId/bid/:bidId/checkout" element={<BidCheckout />} />
          {/* One-time chat is relevant to everyday users; Messages is exposed
              (agreements/wallet pages remain hidden for this surface). */}
          <Route path="messages" element={<ClientMessages />} />
          <Route path="terms" element={<ClientTerms />} />
          <Route path="account" element={<ClientAccount />} />
          <Route path="security" element={<SecuritySettings />} />
          <Route path="*" element={<Navigate to="/everyday/dashboard" replace />} />
        </Routes>
      </EverydayLayout>
    </EverydayGuard>
  )
}

function TransporterPortal() {
  return (
    <TransporterGuard>
      <TransporterLayout>
        <Routes>
          <Route path="dashboard" element={<Dashboard />} />

          <Route path="trucks" element={<MyTrucks />} />
          <Route path="trucks/add" element={<AddTruck />} />
          <Route path="trucks/edit/:id" element={<EditTruck />} />
          <Route path="trucks/config/:id" element={<TruckConfiguration />} />
          <Route path="trucks/:id" element={<TruckDetails />} />
          <Route path="trucks/:id/track" element={<TrackTruck />} />
          <Route path="track" element={<TrackTruck />} />
          {/* <Route path="trucks/:id/service" element={<ServiceHistory />} /> */}
          {/* <Route path="service-history" element={<ServiceHistory />} /> */}

          <Route path="available-bids" element={<AvailableBids />} />
          <Route path="jobs" element={<Navigate to="/transporter/available-bids" replace />} />
          <Route path="my-bids" element={<MyBids />} />
          <Route path="order/:orderId" element={<OrderTracking />} />
          <Route path="bids" element={<MyBids />} />
          <Route path="agreement-bids" element={<TransporterAgreementBids />} />
          <Route path="agreement-jobs" element={<Navigate to="/transporter/agreement-bids" replace />} />
          <Route path="my-agreements" element={<TransporterMyAgreements />} />
          <Route path="messages" element={<TransporterMessages />} />

          <Route path="account-history" element={<AccountHistory />} />

          <Route path="earnings" element={<Earnings />} />
          <Route path="wallet" element={<TransporterWallet />} />

          <Route path="profile" element={<Profile />} />
          <Route path="settings" element={<Settings />} />
          <Route path="security" element={<SecuritySettings />} />

          <Route path="leaderboard" element={<Leaderboard />} />

          <Route path="help" element={<Help />} />
          <Route path="about" element={<About />} />
          <Route path="contact" element={<Contact />} />
          <Route path="terms" element={<Terms />} />
          <Route path="privacy" element={<Privacy />} />
          <Route
            path="*"
            element={
              <TransporterPlaceholderPage
                title="Coming Soon"
                description="This transporter section is still being prepared."
                withLayout={false}
              />
            }
          />
        </Routes>
      </TransporterLayout>
    </TransporterGuard>
  )
}

function DriverPortal() {
  return (
    <DriverGuard>
      <DriverLayout>
        <Routes>
          <Route path="dashboard" element={<DriverDashboard />} />
          <Route path="active-trip" element={<DriverActiveTrip />} />
          <Route path="trips" element={<DriverTrips />} />
          <Route path="fuel-logs" element={<DriverFuelLogs />} />
          <Route path="wallet" element={<DriverWallet />} />
          <Route path="reputation" element={<DriverReputation />} />
          <Route path="profile" element={<DriverProfile />} />
          <Route path="*" element={<DriverDashboard />} />
        </Routes>
      </DriverLayout>
    </DriverGuard>
  )
}

function OrgPortal() {
  return <OrgUnavailablePage />
}

export default function App() {
  return (
    <BrowserRouter>
      <GenuineActivity />
      <AccessLockProvider>
        <StepUpProvider>
        <ActivityTracker>
          <>
          <Routes>
            <Route path="/" element={<Login />} />
            <Route path="/login" element={<Login />} />
            <Route path="/main" element={<MainPage />} />
            <Route path="/signup" element={<SignupWizardProvider />}>
              <Route index element={<Signup />} />
              <Route path="role" element={<RequireSignupBasic><RoleSelect /></RequireSignupBasic>} />
              <Route path="terms" element={<RequireSignupBasic><SignupTerms /></RequireSignupBasic>} />
              <Route path="details/service-seeker" element={<RequireSignupDraft role="service_seeker"><ServiceSeekerDetails /></RequireSignupDraft>} />
              <Route path="details/logistics-provider" element={<RequireSignupDraft role="logistics_provider"><LogisticsProviderDetails /></RequireSignupDraft>} />
              <Route path="details/everyday-user" element={<RequireSignupDraft role="everyday_user"><EverydayUserDetails /></RequireSignupDraft>} />
              <Route path="details/driver" element={<RequireSignupDraft role="driver"><DriverDetails /></RequireSignupDraft>} />
              <Route path="*" element={<Navigate to="/signup" replace />} />
            </Route>
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/unlock" element={<UnlockRoute />} />
            <Route path="/admin/login" element={<AdminLogin />} />
            <Route path="/admin/*" element={<AdminPortal />} />

            <Route path="/transporter-dashboard" element={<Navigate to="/transporter/dashboard" replace />} />
            <Route path="/transporter/*" element={<TransporterPortal />} />
            <Route path="/client/*" element={<ClientPortal />} />
            <Route path="/everyday/*" element={<EverydayPortal />} />
            <Route path="/org/*" element={<OrgPortal />} />
            <Route path="/driver/*" element={<DriverPortal />} />

            <Route path="*" element={<Login />} />
          </Routes>
          <InsuranceReminder />
          </>
        </ActivityTracker>
        </StepUpProvider>
      </AccessLockProvider>
    </BrowserRouter>
  )
}
