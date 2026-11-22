let activeStepUpHandler = null

/**
 * Register the active admin step-up modal prompt handler.
 * Returns a cleanup callback to unregister when unmounted.
 */
export function registerAdminStepUpHandler(handler) {
  activeStepUpHandler = handler
  return () => {
    if (activeStepUpHandler === handler) activeStepUpHandler = null
  }
}

/**
 * Trigger the administrator reauthentication modal for an action-bound 428 challenge.
 */
export async function requestAdminStepUp(actionDescriptor) {
  if (typeof activeStepUpHandler !== 'function') {
    throw new Error('Fresh administrator password verification is required. Please verify via an active Admin workspace.')
  }
  return activeStepUpHandler(actionDescriptor)
}
