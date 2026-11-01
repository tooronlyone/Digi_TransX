import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import InsuranceReminder from '../src/components/common/InsuranceReminder'
import { showInsuranceReminder } from '../src/lib/insuranceReminder'

afterEach(() => { cleanup(); vi.useRealTimers() })

describe('insurance reminder', () => {
  it('appears on success event and disappears at 10 seconds', () => {
    vi.useFakeTimers()
    render(<InsuranceReminder />)
    expect(screen.queryByRole('status')).toBeNull()
    act(() => showInsuranceReminder())
    expect(screen.getByRole('status').textContent).toContain('Consider goods insurance')
    act(() => vi.advanceTimersByTime(9999))
    expect(screen.queryByRole('status')).not.toBeNull()
    act(() => vi.advanceTimersByTime(1))
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('can be dismissed and a later reminder gets a fresh 10 seconds', () => {
    vi.useFakeTimers()
    render(<InsuranceReminder />)
    act(() => showInsuranceReminder())
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss insurance reminder' }))
    expect(screen.queryByRole('status')).toBeNull()
    act(() => { vi.advanceTimersByTime(5000); showInsuranceReminder() })
    act(() => vi.advanceTimersByTime(5000))
    expect(screen.queryByRole('status')).not.toBeNull()
    act(() => vi.advanceTimersByTime(5000))
    expect(screen.queryByRole('status')).toBeNull()
  })
})
