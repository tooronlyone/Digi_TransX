import { describe, expect, it } from 'vitest'
import { pickupBounds, pickupScheduleError } from '../src/lib/pickupSchedule'

const now = Date.parse('2026-10-27T23:00:00+05:00')

describe('Pakistan pickup window', () => {
  it('allows the next day up to the same time, including midnight', () => {
    expect(pickupBounds(now)).toEqual({
      earliest: { date: '2026-10-27', time: '23:20' },
      latest: { date: '2026-10-28', time: '23:00' },
    })
    expect(pickupScheduleError('2026-10-28', '00:00', now)).toBe('')
    expect(pickupScheduleError('2026-10-28', '23:00', now)).toBe('')
    expect(pickupScheduleError('2026-10-28', '23:01', now)).toContain('24 hours')
    expect(pickupScheduleError('2026-10-29', '00:00', now)).toContain('24 hours')
  })

  it('keeps preparation time and rounds the earliest selectable minute up', () => {
    expect(pickupScheduleError('2026-10-27', '23:19', now)).toContain('20 minutes')
    expect(pickupScheduleError('2026-10-27', '23:20', now)).toBe('')
    expect(pickupBounds(now + 1000).earliest.time).toBe('23:21')
    expect(pickupBounds(now + 50 * 60_000).earliest).toEqual({ date: '2026-10-28', time: '00:10' })
  })
})

