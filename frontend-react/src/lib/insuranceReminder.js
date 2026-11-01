export const INSURANCE_REMINDER_EVENT = 'digitransx:insurance-reminder'

export function showInsuranceReminder() {
  window.dispatchEvent(new Event(INSURANCE_REMINDER_EVENT))
}
