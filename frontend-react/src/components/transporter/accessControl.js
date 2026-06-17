export function getTransporterAllowedPaths(user) {
  return Array.isArray(user?.organization_allowed_paths) ? user.organization_allowed_paths : []
}

export function getTransporterDefaultRoute(user) {
  return user?.organization_default_route || '/transporter/dashboard'
}

export function isTransporterPathAllowed(user, path) {
  const allowedPaths = getTransporterAllowedPaths(user)
  if (!allowedPaths.length) return true
  return allowedPaths.some((prefix) => path === prefix || path.startsWith(`${prefix}/`))
}
