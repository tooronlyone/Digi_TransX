import React from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import ActivityTracker from './components/ActivityTracker'
import GlobalAiAssistant from './components/ai/GlobalAiAssistant'

import Login from './pages/auth/Login'
import Signup from './pages/auth/Signup'
import RoleSelect from './pages/auth/RoleSelect'
import ResetPassword from './pages/auth/ResetPassword'
import Unlock from './pages/auth/Unlock'
import MainPage from './pages/main/MainPage'

import ServiceSeekerDetails from './pages/auth/roledetails/ServiceSeekerDetails'
import LogisticsProviderDetails from './pages/auth/roledetails/LogisticsProviderDetails'
import EverydayUserDetails from './pages/auth/roledetails/EverydayUserDetails'
import FuelStationDetails from './pages/auth/roledetails/FuelStationDetails'
import ShopkeeperDetails from './pages/auth/roledetails/ShopkeeperDetails'

import TransporterGuard from './components/transporter/TransporterGuard'
import TransporterLayout from './components/transporter/TransporterLayout'
import ShopkeeperGuard from './components/shopkeeper/ShopkeeperGuard'
import TransporterPlaceholderPage from './components/transporter/TransporterPlaceholderPage'
import ClientLayout from './components/client/ClientLayout'
import useClientAuth from './hooks/useClientAuth'

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
import Partner from './pages/transporter/partner_with_us'
import AiChat from './pages/shared/AiChat'
import ShopkeeperDashboard from './pages/shopkeeper/ShopkeeperDashboard'
import CreateTable from './pages/shopkeeper/CreateTable'
import TableView from './pages/shopkeeper/TableView'
import AnalysisView from './pages/shopkeeper/AnalysisView'
import InventoryPage from './pages/shopkeeper/InventoryPage'
import POSPage from './pages/shopkeeper/POSPage'
import SalesAnalyticsPage from './pages/shopkeeper/SalesAnalyticsPage'
import OrgUserRegister from './pages/org/user/Register'
import OrgUserLogin from './pages/org/user/Login'
import OrgUserDepartments from './pages/org/user/Departments'
import OrgUserDepartmentLogin from './pages/org/user/DepartmentLogin'
import OrgUserDepartmentPortal from './pages/org/user/DepartmentPortal'
import OrgAdminRegister from './pages/org/admin/Register'
import OrgAdminLogin from './pages/org/admin/Login'
import OrgAdminDashboard from './pages/org/admin/Dashboard'
import OrgAdminDepartments from './pages/org/admin/Departments'
import OrgAdminActivity from './pages/org/admin/Activity'
import OrgAdminPartners from './pages/org/admin/Partners'
import OrgAdminTransporterProfile from './pages/org/admin/TransporterProfile'
import OrgPartnerLogin from './pages/org/partner/Login'
import OrgPartnerDashboard from './pages/org/partner/Dashboard'
import OrgPartnerDepartments from './pages/org/partner/Departments'
import OrgPartnerActivity from './pages/org/partner/Activity'
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
  const [status, setStatus] = React.useState('checking')

  React.useEffect(() => {
    fetch('/auth/me', { credentials: 'include' })
      .then(r => r.json())
      .then(data => {
        if (data.success && data.user?.role === 'platform_admin') {
          setStatus('allowed')
        } else {
          setStatus('denied')
        }
      })
      .catch(() => setStatus('denied'))
  }, [])

  if (status === 'checking') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-cyan-500 border-t-transparent" />
      </div>
    )
  }

  if (status === 'denied') {
    return <Navigate to="/admin/login" replace />
  }

  return children
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
          <Route path="agreements" element={<Agreements />} />
          <Route path="post-agreement" element={<PostAgreement />} />
          <Route path="agreement-bids/:postId" element={<ClientAgreementBids />} />
          <Route path="my-agreements" element={<ClientMyAgreements />} />
          <Route path="agreement/:id" element={<AgreementDetail />} />
          <Route path="wallet" element={<Wallet />} />
          <Route path="balance" element={<Wallet />} />
          <Route path="account" element={<ClientAccount />} />
          <Route path="messages" element={<ClientMessages />} />
          <Route path="terms" element={<ClientTerms />} />
          <Route path="*" element={<Navigate to="/client/dashboard" replace />} />
        </Routes>
      </ClientLayout>
    </ClientGuard>
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

          <Route path="leaderboard" element={<Leaderboard />} />

          <Route path="help" element={<Help />} />
          <Route path="about" element={<About />} />
          <Route path="contact" element={<Contact />} />
          <Route path="terms" element={<Terms />} />
          <Route path="privacy" element={<Privacy />} />
          <Route path="partner" element={<Partner />} />
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

function ShopkeeperPortal() {
  return (
    <ShopkeeperGuard>
      <Routes>
        <Route path="dashboard" element={<ShopkeeperDashboard />} />
        <Route path="create-table" element={<CreateTable />} />
        <Route path="table/:tableId" element={<TableView />} />
        <Route path="table/:tableId/analysis" element={<AnalysisView />} />
        <Route path="inventory" element={<InventoryPage />} />
        <Route path="pos" element={<POSPage />} />
        <Route path="sales-analytics" element={<SalesAnalyticsPage />} />
        <Route path="*" element={<ShopkeeperDashboard />} />
      </Routes>
    </ShopkeeperGuard>
  )
}

function OrgPortal() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/org/user/login" replace />} />
      <Route path="user/register" element={<OrgUserRegister />} />
      <Route path="user/register.html" element={<OrgUserRegister />} />
      <Route path="user/login" element={<OrgUserLogin />} />
      <Route path="user/login.html" element={<OrgUserLogin />} />
      <Route path="user/departments" element={<OrgUserDepartments />} />
      <Route path="user/departments.html" element={<OrgUserDepartments />} />
      <Route path="user/department-login" element={<OrgUserDepartmentLogin />} />
      <Route path="user/department_login.html" element={<OrgUserDepartmentLogin />} />
      <Route path="user/department-portal" element={<OrgUserDepartmentPortal />} />
      <Route path="user/department_portal.html" element={<OrgUserDepartmentPortal />} />

      <Route path="admin/register" element={<OrgAdminRegister />} />
      <Route path="admin/register.html" element={<OrgAdminRegister />} />
      <Route path="admin/login" element={<OrgAdminLogin />} />
      <Route path="admin/login.html" element={<OrgAdminLogin />} />
      <Route path="admin/dashboard" element={<OrgAdminDashboard />} />
      <Route path="admin/dashboard.html" element={<OrgAdminDashboard />} />
      <Route path="admin/departments" element={<OrgAdminDepartments />} />
      <Route path="admin/departments.html" element={<OrgAdminDepartments />} />
      <Route path="admin/activity" element={<OrgAdminActivity />} />
      <Route path="admin/activity.html" element={<OrgAdminActivity />} />
      <Route path="admin/partners" element={<OrgAdminPartners />} />
      <Route path="admin/partners.html" element={<OrgAdminPartners />} />
      <Route path="admin/transporter-profile" element={<OrgAdminTransporterProfile />} />
      <Route path="admin/transporter_profile.html" element={<OrgAdminTransporterProfile />} />

      <Route path="partner/login" element={<OrgPartnerLogin />} />
      <Route path="partner/login.html" element={<OrgPartnerLogin />} />
      <Route path="partner/dashboard" element={<OrgPartnerDashboard />} />
      <Route path="partner/dashboard.html" element={<OrgPartnerDashboard />} />
      <Route path="partner/departments" element={<OrgPartnerDepartments />} />
      <Route path="partner/departments.html" element={<OrgPartnerDepartments />} />
      <Route path="partner/activity" element={<OrgPartnerActivity />} />
      <Route path="partner/activity.html" element={<OrgPartnerActivity />} />

      <Route path="*" element={<Navigate to="/org/user/login" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <ActivityTracker>
        <>
          <Routes>
            <Route path="/" element={<Login />} />
            <Route path="/login" element={<Login />} />
            <Route path="/main" element={<MainPage />} />
            <Route path="/signup" element={<Signup />} />
            <Route path="/signup/role" element={<RoleSelect />} />
            <Route path="/signup/details/service-seeker" element={<ServiceSeekerDetails />} />
            <Route path="/signup/details/logistics-provider" element={<LogisticsProviderDetails />} />
            <Route path="/signup/details/everyday-user" element={<EverydayUserDetails />} />
            <Route path="/signup/details/fuel-station" element={<FuelStationDetails />} />
            <Route path="/signup/details/shopkeeper" element={<ShopkeeperDetails />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/unlock" element={<Unlock />} />
            <Route path="/ai-chat" element={<AiChat />} />
            <Route path="/admin/login" element={<AdminLogin />} />
            <Route path="/admin/*" element={<AdminPortal />} />

            <Route path="/transporter-dashboard" element={<Navigate to="/transporter/dashboard" replace />} />
            <Route path="/transporter/*" element={<TransporterPortal />} />
            <Route path="/client/*" element={<ClientPortal />} />
            <Route path="/org/*" element={<OrgPortal />} />
            <Route path="/shopkeeper/*" element={<ShopkeeperPortal />} />
            <Route
              path="/fuelstation/dashboard"
              element={
                <TransporterPlaceholderPage
                  title="Fuel Station Dashboard"
                  description="Fuel station portal is being prepared."
                />
              }
            />

            <Route path="*" element={<Login />} />
          </Routes>
          <GlobalAiAssistant />
        </>
      </ActivityTracker>
    </BrowserRouter>
  )
}
