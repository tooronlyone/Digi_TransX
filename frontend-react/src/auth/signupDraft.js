let basicDraft = null
let selectedRole = ''

export function setSignupBasicDraft(value) {
  basicDraft = value && typeof value === 'object' ? { ...value } : null
}

export function getSignupBasicDraft() {
  return basicDraft ? { ...basicDraft } : null
}

export function setSignupRole(role) {
  selectedRole = String(role || '')
}

export function getSignupRole() {
  return selectedRole
}

export function clearSignupDraft() {
  basicDraft = null
  selectedRole = ''
}
