// @vitest-environment jsdom
import React from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import AddTruck from '../src/pages/transporter/add_truck'
import { computeHybridTruckPayload } from '../src/lib/hybridTruckModel'

vi.mock('../src/pages/client/clientUtils', () => ({
  getCsrfToken: vi.fn().mockResolvedValue('test-csrf'),
}))

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('Hybrid Truck Model & AddTruck UI', () => {
  it('computes canonical catalog_type_key, CBM, and safety-locked commodities for Milk Tanker in Liters or Tons', () => {
    const resLiters = computeHybridTruckPayload({
      bodyStyle: 'Tanker',
      tankerUse: 'milk_water',
      tankLiters: '15000',
      capacityUnit: 'liters',
    })
    expect(resLiters.error).toBeNull()
    expect(resLiters.fields.catalog_type_key).toBe('milk_tanker')
    expect(resLiters.fields.volume_max_cbm).toBe('15')
    expect(resLiters.fields.payload_max_tons).toBe('15')
    expect(resLiters.fields.payload_min_tons).toBe('0')
    const specs = JSON.parse(resLiters.fields.catalog_specs_json)
    expect(specs.allowed_commodities).toEqual(['milk', 'water'])

    const resTons = computeHybridTruckPayload({
      bodyStyle: 'Tanker',
      tankerUse: 'milk_water',
      capacityTons: '12',
      capacityUnit: 'tons',
    })
    expect(resTons.error).toBeNull()
    expect(resTons.fields.payload_max_tons).toBe('12')
    expect(resTons.fields.volume_max_cbm).toBe('12')
  })

  it('rejects weight capacity above 100 Tons when unit is Tons to prevent Liters/kg typo', () => {
    const res = computeHybridTruckPayload({
      bodyStyle: 'Open Body',
      sizeClass: 'light_truck_3_5_5_ton',
      allowedCommodities: ['general_cargo'],
      capacityTons: '1000',
      capacityUnit: 'tons',
    })
    expect(res.error).toMatch(/cannot exceed 100 Tons/i)
  })

  it('computes preset dimensions, volume, and selected uses for Open Body truck', () => {
    const res = computeHybridTruckPayload({
      bodyStyle: 'Open Body',
      sizeClass: 'light_truck_3_5_5_ton',
      allowedCommodities: ['general_cargo', 'furniture'],
      capacityTons: '5',
    })
    expect(res.error).toBeNull()
    expect(res.fields.catalog_type_key).toBe('light_truck_3_5_5_ton')
    expect(res.fields.bed_length_ft).toBe('16')
    expect(res.fields.payload_max_tons).toBe('5')
    const specs = JSON.parse(res.fields.catalog_specs_json)
    expect(specs.allowed_commodities).toEqual(['general_cargo', 'furniture'])
  })

  it('shows Tons/Liters toggle only for Liquid Tankers and shows only Tons (capped at 100) for Livestock/Open Body', () => {
    render(
      <MemoryRouter>
        <AddTruck />
      </MemoryRouter>,
    )

    const bodySelect = screen.getByLabelText(/Body Type/i)
    fireEvent.change(bodySelect, { target: { value: 'Tanker' } })

    expect(screen.getByText(/Dedicated Tanker Use/i)).toBeTruthy()
    const tonsInput = screen.getByLabelText(/Max Weight Capacity \(Tons\)/i)
    expect(tonsInput.value).toBe('12')

    // Trying to type 1000 in Tons clamps at 100 and displays a warning
    fireEvent.change(tonsInput, { target: { value: '1000' } })
    expect(tonsInput.value).toBe('100')
    expect(screen.getByText(/Maximum allowed weight is 100 Tons/i)).toBeTruthy()

    // Switch to Liters unit on Liquid Tanker
    const litersBtn = screen.getByRole('button', { name: /^Liters$/i })
    fireEvent.click(litersBtn)

    const litersInput = screen.getByLabelText(/Tank Capacity \(Liters\)/i)
    expect(litersInput.value).toBe('100000')

    // Switch to Livestock -> Liters toggle is hidden, only Tons is shown
    fireEvent.change(bodySelect, { target: { value: 'Livestock' } })
    expect(screen.queryByRole('button', { name: /^Liters$/i })).toBeNull()
    expect(screen.getByLabelText(/Max Weight Capacity \(Tons\)/i)).toBeTruthy()

    // Driver & Tracking / GPS Device IMEI section is completely removed
    expect(screen.queryByText(/Driver & Tracking/i)).toBeNull()
    expect(screen.queryByLabelText(/GPS Device IMEI/i)).toBeNull()
  })
})
