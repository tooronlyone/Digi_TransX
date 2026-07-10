export const FALLBACK_TRUCK_TYPES = [
  { type_key: 'mini_pickup', display_name: 'Mini pickup' },
  { type_key: 'light_truck_2_3_5_ton', display_name: 'Light truck 2-3.5 ton' },
  { type_key: 'light_truck_3_5_5_ton', display_name: 'Light truck 3.5-5 ton' },
  { type_key: 'medium_rigid_truck_5_9_ton', display_name: 'Medium rigid truck 5-9 ton' },
  { type_key: 'heavy_rigid_truck_9_15_ton', display_name: 'Heavy rigid truck 9-15 ton' },
  { type_key: 'heavy_rigid_truck_15_25_ton', display_name: 'Heavy rigid truck 15-25 ton' },
  { type_key: 'flatbed_trailer_open_semi_trailer', display_name: 'Flatbed trailer / open semi-trailer' },
  { type_key: 'container_carrier_skeletal_trailer', display_name: 'Container carrier / skeletal trailer' },
  { type_key: 'low_bed_low_loader_trailer', display_name: 'Low-bed / low-loader trailer' },
  { type_key: 'fuel_oil_tanker', display_name: 'Fuel / oil tanker' },
  { type_key: 'milk_tanker', display_name: 'Milk tanker' },
  { type_key: 'chemical_tanker', display_name: 'Chemical tanker' },
  { type_key: 'refrigerated_rigid_truck', display_name: 'Refrigerated rigid truck' },
  { type_key: 'reefer_trailer_reefer_container_carrier', display_name: 'Reefer trailer / reefer container carrier' },
  { type_key: 'insulated_or_dry_box_truck', display_name: 'Insulated or dry box truck' },
  { type_key: 'dump_truck_tipper', display_name: 'Dump truck / tipper' },
  { type_key: 'bulk_cement_tanker_powder_bulker', display_name: 'Bulk cement tanker / powder bulker' },
  { type_key: 'livestock_carrier', display_name: 'Livestock carrier' },
]

export async function loadTruckCatalog() {
  try {
    const response = await fetch('/api/catalog/truck-types', { credentials: 'same-origin' })
    if (!response.ok) throw new Error('catalog unavailable')
    const data = await response.json()
    const items = data.truck_types || data.items || []
    return items.length ? items : FALLBACK_TRUCK_TYPES
  } catch {
    return FALLBACK_TRUCK_TYPES
  }
}