/**
 * Hybrid Truck Model — Single Source of Truth (Frontend)
 *
 * Bridges the Transporter's 3-Step Registration / Configuration flow:
 *   1. Basic Truck Identity (Truck Number, Company, Model, Chassis)
 *   2. Body Type + Smart Size Class Preset (zero manual Length/Width/Height/CBM math)
 *   3. Safety-Locked Cargo Use + Single Dynamic Capacity (Tons or Liters, capped at 100 Tons)
 *
 * Directly maps to the 18 canonical catalog_type_key values in trucks/helpers.py
 * and the 19 commodity keys in orders/goods_taxonomy.py so both One-Time Orders
 * and Long-Term Agreements match 100% deterministically.
 */

export const MIN_CAPACITY_TONS = 0.3
export const MAX_CAPACITY_TONS = 100
export const MIN_CAPACITY_LITERS = 500
export const MAX_CAPACITY_LITERS = 100000

export const HYBRID_BODY_TYPES = [
  {
    value: 'Open Body',
    label: 'Open Body (Khula Dala)',
    subtitle: 'Shehzore, Mazda, Hino 6-Wheeler, 10-Wheeler open deck trucks',
    icon: 'fa-truck-Ramp-box',
  },
  {
    value: 'Box Body',
    label: 'Box Body (Closed Container)',
    subtitle: 'Enclosed dry or insulated box trucks for weather-protected goods',
    icon: 'fa-truck-moving',
  },
  {
    value: 'Tanker',
    label: 'Tanker (Liquid / Gas / Bulk Powder)',
    subtitle: 'Dedicated food-grade milk/water/oil, fuel, chemical, LPG or cement tankers',
    icon: 'fa-Fill-drip',
  },
  {
    value: 'Trailer',
    label: 'Trailer (20ft / 40ft / Low-Bed)',
    subtitle: 'Heavy 22-wheeler flatbed, skeletal container carrier, or low-loader trailer',
    icon: 'fa-trailer',
  },
  {
    value: 'Refrigerated',
    label: 'Refrigerated (Reefer / Chiller)',
    subtitle: 'Temperature-controlled chiller (0°C to 8°C) or deep freezer (-18°C)',
    icon: 'fa-snowflake',
  },
  {
    value: 'Dumper',
    label: 'Dumper / Tipper',
    subtitle: 'Hydraulic tipper for sand (rait), gravel (bajri), grain, coal & waste',
    icon: 'fa-truck-monster',
  },
  {
    value: 'Livestock',
    label: 'Livestock Carrier',
    subtitle: 'Ventilated carrier for cattle, goats, sheep & poultry',
    icon: 'fa-cow',
  },
]

export const SIZE_CLASS_PRESETS = {
  'Open Body': [
    {
      key: 'mini_pickup',
      title: 'Mini Pickup (Suzuki / Ravi)',
      specLabel: '~8 ft bed · Up to 1 Ton',
      catalog_type_key: 'mini_pickup',
      default_tons: 1,
      bed_length_ft: 8,
      bed_width_ft: 5.5,
      bed_height_ft: 5,
      volume_max_cbm: 5,
    },
    {
      key: 'light_truck_2_3_5_ton',
      title: 'Light Truck (Shehzore / Hyundai)',
      specLabel: '~10 ft bed · 1.5 to 3.5 Ton',
      catalog_type_key: 'light_truck_2_3_5_ton',
      default_tons: 3.5,
      bed_length_ft: 10,
      bed_width_ft: 6.5,
      bed_height_ft: 6.5,
      volume_max_cbm: 18,
    },
    {
      key: 'light_truck_3_5_5_ton',
      title: 'Medium Truck (Mazda 14–16 ft)',
      specLabel: '~16 ft bed · 3.5 to 5 Ton',
      catalog_type_key: 'light_truck_3_5_5_ton',
      default_tons: 5,
      bed_length_ft: 16,
      bed_width_ft: 7,
      bed_height_ft: 7,
      volume_max_cbm: 24,
    },
    {
      key: 'medium_rigid_truck_5_9_ton',
      title: 'Large Mazda (17–20 ft)',
      specLabel: '~19 ft bed · 5 to 9 Ton',
      catalog_type_key: 'medium_rigid_truck_5_9_ton',
      default_tons: 9,
      bed_length_ft: 19,
      bed_width_ft: 7.5,
      bed_height_ft: 8,
      volume_max_cbm: 36,
    },
    {
      key: 'heavy_rigid_truck_9_15_ton',
      title: 'Heavy 6-Wheeler (Hino / Isuzu)',
      specLabel: '~22 ft bed · 9 to 15 Ton',
      catalog_type_key: 'heavy_rigid_truck_9_15_ton',
      default_tons: 15,
      bed_length_ft: 22,
      bed_width_ft: 8,
      bed_height_ft: 8.5,
      volume_max_cbm: 55,
    },
    {
      key: 'heavy_rigid_truck_15_25_ton',
      title: 'Heavy 10-Wheeler (Multi-Axle)',
      specLabel: '~26 ft bed · 15 to 25 Ton',
      catalog_type_key: 'heavy_rigid_truck_15_25_ton',
      default_tons: 25,
      bed_length_ft: 26,
      bed_width_ft: 8,
      bed_height_ft: 9,
      volume_max_cbm: 70,
    },
  ],
  'Box Body': [
    {
      key: 'light_truck_2_3_5_ton',
      title: 'Light Closed Box (Shehzore)',
      specLabel: '~10 ft box · Up to 3.5 Ton',
      catalog_type_key: 'light_truck_2_3_5_ton',
      default_tons: 3.5,
      bed_length_ft: 10,
      bed_width_ft: 6.5,
      bed_height_ft: 6.5,
      volume_max_cbm: 18,
    },
    {
      key: 'light_truck_3_5_5_ton',
      title: 'Medium Closed Box (Mazda 16 ft)',
      specLabel: '~16 ft box · 3.5 to 5 Ton',
      catalog_type_key: 'light_truck_3_5_5_ton',
      default_tons: 5,
      bed_length_ft: 16,
      bed_width_ft: 7,
      bed_height_ft: 7.5,
      volume_max_cbm: 24,
    },
    {
      key: 'medium_rigid_truck_5_9_ton',
      title: 'Large Closed Box (19 ft)',
      specLabel: '~19 ft box · 5 to 9 Ton',
      catalog_type_key: 'medium_rigid_truck_5_9_ton',
      default_tons: 9,
      bed_length_ft: 19,
      bed_width_ft: 7.5,
      bed_height_ft: 8,
      volume_max_cbm: 36,
    },
    {
      key: 'insulated_or_dry_box_truck',
      title: 'Heavy Dry / Insulated Box (22–24 ft)',
      specLabel: '~24 ft box · 9 to 15 Ton',
      catalog_type_key: 'insulated_or_dry_box_truck',
      default_tons: 12,
      bed_length_ft: 24,
      bed_width_ft: 8,
      bed_height_ft: 8.5,
      volume_max_cbm: 45,
    },
  ],
  Trailer: [
    {
      key: 'flatbed_trailer_open_semi_trailer',
      title: '40ft Open Flatbed Trailer',
      specLabel: '40 ft open bed · Steel (Sariya), Pipes, Bales & Machinery',
      catalog_type_key: 'flatbed_trailer_open_semi_trailer',
      default_tons: 35,
      bed_length_ft: 40,
      bed_width_ft: 8.5,
      bed_height_ft: 10,
      volume_max_cbm: 85,
    },
    {
      key: 'container_carrier_skeletal_trailer',
      title: '20ft / 40ft Container Carrier (Skeletal)',
      specLabel: '40 ft skeletal chassis · Standard Shipping Containers',
      catalog_type_key: 'container_carrier_skeletal_trailer',
      default_tons: 30,
      bed_length_ft: 40,
      bed_width_ft: 8.5,
      bed_height_ft: 10,
      volume_max_cbm: 85,
    },
    {
      key: 'low_bed_low_loader_trailer',
      title: '45ft Low-Bed / Low-Loader Trailer',
      specLabel: '45 ft low deck · Heavy Excavators, Boilers & Oversized Loads',
      catalog_type_key: 'low_bed_low_loader_trailer',
      default_tons: 50,
      bed_length_ft: 45,
      bed_width_ft: 10,
      bed_height_ft: 12,
      volume_max_cbm: 100,
    },
  ],
  Refrigerated: [
    {
      key: 'refrigerated_rigid_truck',
      title: 'Refrigerated Rigid Truck (Chiller / Freezer Box)',
      specLabel: '~20 ft insulated box · 1 to 12 Ton',
      catalog_type_key: 'refrigerated_rigid_truck',
      default_tons: 8,
      bed_length_ft: 20,
      bed_width_ft: 8,
      bed_height_ft: 8,
      volume_max_cbm: 40,
    },
    {
      key: 'reefer_trailer_reefer_container_carrier',
      title: '40ft Reefer Trailer / Container Carrier',
      specLabel: '40 ft heavy cold-chain · 12 to 28 Ton',
      catalog_type_key: 'reefer_trailer_reefer_container_carrier',
      default_tons: 25,
      bed_length_ft: 40,
      bed_width_ft: 8.5,
      bed_height_ft: 9,
      volume_max_cbm: 75,
    },
  ],
}

/**
 * Safety-locked Tanker Purposes (Single-Select Radio).
 * Prevents food-grade vs fuel/chemical cross-contamination.
 */
export const TANKER_USE_OPTIONS = [
  {
    key: 'milk_water',
    label: 'Milk & Potable Water (Food-Grade Dairy Tanker)',
    badge: 'Food-Grade Only',
    catalog_type_key: 'milk_tanker',
    allowed_commodities: ['milk', 'water'],
    capacity_mode: 'liters',
    default_tons: 12,
    default_liters: 12000,
    refrigerated: true,
    hazardous: false,
  },
  {
    key: 'edible_oil',
    label: 'Edible / Cooking Oil (Food-Grade Oil Tanker)',
    badge: 'Food-Grade Only',
    catalog_type_key: 'fuel_oil_tanker',
    allowed_commodities: ['edible_oil'],
    capacity_mode: 'liters',
    default_tons: 15,
    default_liters: 15000,
    refrigerated: false,
    hazardous: false,
  },
  {
    key: 'fuel',
    label: 'Petrol / Diesel / Furnace Oil (Fuel Tanker)',
    badge: 'Hazardous Fuel',
    catalog_type_key: 'fuel_oil_tanker',
    allowed_commodities: ['fuel'],
    capacity_mode: 'liters',
    default_tons: 25,
    default_liters: 25000,
    refrigerated: false,
    hazardous: true,
  },
  {
    key: 'chemicals_liquid',
    label: 'Chemicals / Industrial Liquids (Chemical Tanker)',
    badge: 'Hazardous Chemical',
    catalog_type_key: 'chemical_tanker',
    allowed_commodities: ['chemicals_liquid'],
    capacity_mode: 'liters',
    default_tons: 20,
    default_liters: 20000,
    refrigerated: false,
    hazardous: true,
  },
  {
    key: 'lpg_cng',
    label: 'LPG / CNG / Industrial Gas (Pressurized Bowzer)',
    badge: 'Hazardous Gas',
    catalog_type_key: 'chemical_tanker',
    allowed_commodities: ['lpg_cng'],
    capacity_mode: 'tons',
    default_tons: 20,
    default_liters: 20000,
    refrigerated: false,
    hazardous: true,
  },
  {
    key: 'cement',
    label: 'Bulk Cement / Fly Ash Powder (Pneumatic Bulker)',
    badge: 'Dry Bulk Powder',
    catalog_type_key: 'bulk_cement_tanker_powder_bulker',
    allowed_commodities: ['cement', 'grain'],
    capacity_mode: 'tons',
    default_tons: 30,
    default_liters: 30000,
    refrigerated: false,
    hazardous: false,
  },
]

export const REEFER_TEMPERATURE_OPTIONS = [
  {
    value: 'Chilled (0C to 8C)',
    label: 'Chilled Only (0°C to +8°C)',
    subtitle: 'Fruits, Vegetables, Fresh Dairy & Pharmaceuticals',
    allowed_commodities: ['fruits_vegetables', 'pharmaceuticals'],
  },
  {
    value: 'Frozen (-18C)',
    label: 'Deep Frozen (-18°C)',
    subtitle: 'Frozen Meat, Ice Cream & Frozen Foods',
    allowed_commodities: ['frozen_food'],
  },
  {
    value: 'Both',
    label: 'Dual-Temp (-18°C Frozen & 0°C to +8°C Chilled)',
    subtitle: 'Supports all Frozen, Chilled, Produce & Pharma orders',
    allowed_commodities: ['frozen_food', 'fruits_vegetables', 'pharmaceuticals'],
  },
]

export const CARGO_USE_OPTIONS_BY_BODY = {
  'Open Body': [
    { key: 'general_cargo', label: 'General / Mixed Cargo & Cartons' },
    { key: 'furniture', label: 'Furniture & Household Shifting' },
    { key: 'cotton_textiles', label: 'Cotton / Textiles / Bales' },
    { key: 'machinery', label: 'Machinery, Steel (Sariya) & Pipes' },
    { key: 'electronics', label: 'Packaged Electronics & Appliances' },
    { key: 'fruits_vegetables', label: 'Fresh Fruits & Vegetables (Mandis)' },
  ],
  'Box Body': [
    { key: 'general_cargo', label: 'General / Mixed Cargo & FMCG' },
    { key: 'electronics', label: 'Electronics & Home Appliances' },
    { key: 'furniture', label: 'Furniture & Household Goods' },
    { key: 'cotton_textiles', label: 'Textiles / Garments / Bales' },
    { key: 'fruits_vegetables', label: 'Perishable Fruits & Vegetables' },
    { key: 'pharmaceuticals', label: 'Insulated Pharmaceuticals & Medical Supplies' },
  ],
  Trailer: [
    { key: 'general_cargo', label: 'Shipping Containers & Heavy General Cargo' },
    { key: 'machinery', label: 'Heavy Machinery, Steel (Sariya), Girders & Pipes' },
    { key: 'cotton_textiles', label: 'Cotton / Textile Bales (Export)' },
    { key: 'furniture', label: 'Containerized Furniture & Commercial Goods' },
    { key: 'electronics', label: 'Containerized Electronics & Appliances' },
  ],
  Dumper: [
    { key: 'sand_gravel', label: 'Sand / Gravel / Crush (Rait, Bajri, Pathar)' },
    { key: 'grain', label: 'Bulk Grain / Wheat / Rice' },
    { key: 'coal_minerals', label: 'Coal / Minerals / Ore' },
    { key: 'waste', label: 'Construction Debris & Earthmoving' },
  ],
}

export const LIVESTOCK_ANIMAL_OPTIONS = ['Cattle', 'Goats', 'Sheep', 'Poultry']

/**
 * Normalize legacy body_style values (e.g. 'Dumper / Tipper' -> 'Dumper').
 */
export function normalizeBodyStyle(raw) {
  const s = String(raw || '').trim()
  if (!s) return ''
  if (s === 'Dumper / Tipper' || s.toLowerCase().includes('tipper') || s.toLowerCase().includes('dumper')) {
    return 'Dumper'
  }
  return s
}

/**
 * Given the user's current Hybrid UI selections, compute all canonical backend
 * fields and validate completeness.
 *
 * Supports capacity entry in either 'tons' (default, capped at 100 Tons) or
 * 'liters' (500 to 100,000 Liters, auto-converted at 1,000 Liters = 1 Ton = 1 CBM).
 */
export function computeHybridTruckPayload({
  bodyStyle,
  sizeClass,
  tankerUse,
  temperatureRange,
  allowedCommodities = [],
  livestockTypes = [],
  capacityTons,
  tankLiters,
  capacityUnit,
}) {
  const body = normalizeBodyStyle(bodyStyle)
  if (!body) {
    return { error: 'Please select a Body Type.' }
  }

  const effectiveUnit =
    capacityUnit === 'liters' || capacityUnit === 'tons'
      ? capacityUnit
      : capacityTons !== undefined && capacityTons !== '' && capacityTons !== null
        ? 'tons'
        : tankLiters !== undefined && tankLiters !== '' && tankLiters !== null
          ? 'liters'
          : 'tons'

  let payloadMaxTons = 0
  let resolvedTankLiters = null

  if (effectiveUnit === 'liters') {
    const liters = Number(tankLiters)
    if (!Number.isFinite(liters) || liters <= 0) {
      return { error: 'Please enter a valid capacity in Liters (e.g. 12000).' }
    }
    if (liters < MIN_CAPACITY_LITERS) {
      return {
        error: `Capacity in Liters must be at least ${MIN_CAPACITY_LITERS} Liters (0.5 Ton). If you meant Tons, please switch the unit to Tons.`,
      }
    }
    if (liters > MAX_CAPACITY_LITERS) {
      return {
        error: `Capacity cannot exceed ${MAX_CAPACITY_LITERS.toLocaleString()} Liters (${MAX_CAPACITY_TONS} Tons).`,
      }
    }
    resolvedTankLiters = Math.round(liters)
    payloadMaxTons = Number((liters / 1000).toFixed(2))
  } else {
    const tons = Number(capacityTons)
    if (!Number.isFinite(tons) || tons <= 0) {
      return { error: 'Please enter a valid Max Weight Capacity in Tons.' }
    }
    if (tons > MAX_CAPACITY_TONS) {
      return {
        error: `Max capacity cannot exceed ${MAX_CAPACITY_TONS} Tons. If you are entering Liters (e.g. 12000), please switch the unit to Liters.`,
      }
    }
    payloadMaxTons = Number(tons.toFixed(2))
    if (body === 'Tanker') {
      resolvedTankLiters = Math.round(payloadMaxTons * 1000)
    }
  }

  let catalogTypeKey = ''
  let bedLengthFt = 20
  let bedWidthFt = 8
  let bedHeightFt = 8
  let volumeMaxCbm = 35
  let resolvedCommodities = [...allowedCommodities]
  let refrigerationSupported = false
  let hazardousSupported = false
  let fragileSupported = true
  let detailTypeLabel = body

  if (body === 'Tanker') {
    const tankerOpt = TANKER_USE_OPTIONS.find((o) => o.key === tankerUse)
    if (!tankerOpt) {
      return { error: 'Please select what this Tanker is used to transport.' }
    }
    catalogTypeKey = tankerOpt.catalog_type_key
    resolvedCommodities = [...tankerOpt.allowed_commodities]
    refrigerationSupported = !!tankerOpt.refrigerated
    hazardousSupported = !!tankerOpt.hazardous
    detailTypeLabel = tankerOpt.label
    bedLengthFt = 24
    bedWidthFt = 8
    bedHeightFt = 8

    if (tankerOpt.capacity_mode === 'liters' || effectiveUnit === 'liters') {
      const litersForVolume = resolvedTankLiters || Math.round(payloadMaxTons * 1000)
      resolvedTankLiters = litersForVolume
      volumeMaxCbm = Number((litersForVolume / 1000).toFixed(3))
    } else {
      volumeMaxCbm = Math.max(45, Number((payloadMaxTons * 1.5).toFixed(1)))
    }
  } else if (body === 'Refrigerated') {
    const presets = SIZE_CLASS_PRESETS.Refrigerated
    const preset = presets.find((p) => p.key === sizeClass) || presets[0]
    if (!sizeClass) {
      return { error: 'Please select the Refrigerated Truck Size.' }
    }
    const tempOpt = REEFER_TEMPERATURE_OPTIONS.find((t) => t.value === temperatureRange)
    if (!tempOpt) {
      return { error: 'Please select the Cooling / Temperature Range.' }
    }
    catalogTypeKey = preset.catalog_type_key
    bedLengthFt = preset.bed_length_ft
    bedWidthFt = preset.bed_width_ft
    bedHeightFt = preset.bed_height_ft
    volumeMaxCbm = Math.max(preset.volume_max_cbm, Number((payloadMaxTons * 3.5).toFixed(1)))
    resolvedCommodities = [...tempOpt.allowed_commodities]
    refrigerationSupported = true
    detailTypeLabel = `${preset.title} (${tempOpt.value})`
  } else if (body === 'Dumper') {
    if (resolvedCommodities.length === 0) {
      resolvedCommodities = ['sand_gravel', 'grain', 'coal_minerals', 'waste']
    }
    catalogTypeKey = 'dump_truck_tipper'
    bedLengthFt = 20
    bedWidthFt = 8
    bedHeightFt = 6
    volumeMaxCbm = Math.max(25, Number((payloadMaxTons * 1.5).toFixed(1)))
    detailTypeLabel = 'Dump Truck / Tipper'
  } else if (body === 'Livestock') {
    if (livestockTypes.length === 0) {
      return { error: 'Please select at least one Livestock Type.' }
    }
    catalogTypeKey = 'livestock_carrier'
    resolvedCommodities = ['livestock']
    bedLengthFt = 22
    bedWidthFt = 8
    bedHeightFt = 8
    volumeMaxCbm = 45
    detailTypeLabel = `Livestock (${livestockTypes.join(', ')})`
  } else if (body === 'Open Body' || body === 'Box Body' || body === 'Trailer') {
    const presets = SIZE_CLASS_PRESETS[body] || []
    const preset = presets.find((p) => p.key === sizeClass)
    if (!preset) {
      return { error: `Please select the ${body} Size / Class.` }
    }
    if (resolvedCommodities.length === 0) {
      return { error: 'Please select at least one Cargo Use for this truck.' }
    }
    catalogTypeKey = preset.catalog_type_key
    bedLengthFt = preset.bed_length_ft
    bedWidthFt = preset.bed_width_ft
    bedHeightFt = preset.bed_height_ft
    volumeMaxCbm = Math.max(preset.volume_max_cbm, Number((payloadMaxTons * 3).toFixed(1)))
    detailTypeLabel = preset.title
  } else {
    catalogTypeKey = sizeClass || 'medium_rigid_truck_5_9_ton'
    resolvedCommodities = resolvedCommodities.length ? resolvedCommodities : ['general_cargo']
  }

  const specsJson = {
    hybrid_version: 2,
    body_type: body,
    size_class: sizeClass || catalogTypeKey,
    catalog_type_key: catalogTypeKey,
    detail_type: detailTypeLabel,
    allowed_commodities: resolvedCommodities,
    capacity_input_unit: effectiveUnit,
    tanker_use: body === 'Tanker' ? tankerUse : '',
    tank_capacity_liters: body === 'Tanker' && resolvedTankLiters ? resolvedTankLiters : null,
    temperature_range: body === 'Refrigerated' ? temperatureRange : '',
    livestock_types: body === 'Livestock' ? livestockTypes : [],
  }

  return {
    error: null,
    fields: {
      body_style: body,
      catalog_type_key: catalogTypeKey,
      truckType: body,
      truck_type: body,
      mainUse: detailTypeLabel,
      payload_min_tons: '0',
      payload_max_tons: String(payloadMaxTons),
      max_capacity: String(payloadMaxTons),
      capacity: String(payloadMaxTons),
      volume_min_cbm: '0',
      volume_max_cbm: String(volumeMaxCbm),
      bed_length_ft: String(bedLengthFt),
      bed_width_ft: String(bedWidthFt),
      bed_height_ft: String(bedHeightFt),
      refrigeration_supported: refrigerationSupported ? '1' : '0',
      hazardous_supported: hazardousSupported ? '1' : '0',
      fragile_supported: fragileSupported ? '1' : '0',
      catalog_specs_json: JSON.stringify(specsJson),
    },
  }
}

/**
 * Hydrate the Hybrid Truck UI state from a saved truck / configuration record.
 */
export function extractHybridStateFromTruck(cfg = {}) {
  let specs = {}
  if (cfg.catalog_specs_json) {
    if (typeof cfg.catalog_specs_json === 'object') {
      specs = cfg.catalog_specs_json
    } else if (typeof cfg.catalog_specs_json === 'string') {
      try {
        const parsed = JSON.parse(cfg.catalog_specs_json)
        if (parsed && typeof parsed === 'object') specs = parsed
      } catch {
        specs = {}
      }
    }
  }

  const validBodies = new Set(HYBRID_BODY_TYPES.map((b) => b.value))
  let bodyType = normalizeBodyStyle(cfg.body_style || specs.body_type || '')
  const catKey = String(cfg.catalog_type_key || specs.catalog_type_key || '').trim()

  if (!validBodies.has(bodyType)) {
    if (['milk_tanker', 'fuel_oil_tanker', 'chemical_tanker', 'bulk_cement_tanker_powder_bulker'].includes(catKey)) {
      bodyType = 'Tanker'
    } else if (['refrigerated_rigid_truck', 'reefer_trailer_reefer_container_carrier'].includes(catKey)) {
      bodyType = 'Refrigerated'
    } else if (['flatbed_trailer_open_semi_trailer', 'container_carrier_skeletal_trailer', 'low_bed_low_loader_trailer'].includes(catKey)) {
      bodyType = 'Trailer'
    } else if (catKey === 'dump_truck_tipper') {
      bodyType = 'Dumper'
    } else if (catKey === 'livestock_carrier') {
      bodyType = 'Livestock'
    } else if (catKey === 'insulated_or_dry_box_truck') {
      bodyType = 'Box Body'
    } else if (catKey) {
      bodyType = 'Open Body'
    } else {
      bodyType = ''
    }
  }

  const presets = SIZE_CLASS_PRESETS[bodyType] || []
  let sizeClass = ''
  if (presets.length > 0) {
    const matchBySpec = presets.find((p) => p.key === specs.size_class)
    const matchByCat = presets.find((p) => p.catalog_type_key === catKey)
    sizeClass = matchBySpec?.key || matchByCat?.key || presets[0].key
  }

  let tankerUse = ''
  if (bodyType === 'Tanker') {
    const matchTanker = TANKER_USE_OPTIONS.find((o) => o.key === specs.tanker_use)
    if (matchTanker) {
      tankerUse = matchTanker.key
    } else if (catKey === 'milk_tanker') {
      tankerUse = 'milk_water'
    } else if (catKey === 'fuel_oil_tanker') {
      tankerUse = 'fuel'
    } else if (catKey === 'chemical_tanker') {
      tankerUse = 'chemicals_liquid'
    } else if (catKey === 'bulk_cement_tanker_powder_bulker') {
      tankerUse = 'cement'
    } else {
      tankerUse = TANKER_USE_OPTIONS[0].key
    }
  }

  const temperatureRange =
    REEFER_TEMPERATURE_OPTIONS.find((t) => t.value === specs.temperature_range)?.value || 'Both'

  let allowedCommodities = []
  if (Array.isArray(specs.allowed_commodities) && specs.allowed_commodities.length > 0) {
    allowedCommodities = [...specs.allowed_commodities]
  } else if (bodyType === 'Tanker') {
    const tOpt = TANKER_USE_OPTIONS.find((o) => o.key === tankerUse) || TANKER_USE_OPTIONS[0]
    allowedCommodities = [...tOpt.allowed_commodities]
  } else if (bodyType === 'Refrigerated') {
    const rOpt = REEFER_TEMPERATURE_OPTIONS.find((t) => t.value === temperatureRange) || REEFER_TEMPERATURE_OPTIONS[2]
    allowedCommodities = [...rOpt.allowed_commodities]
  } else if (bodyType === 'Livestock') {
    allowedCommodities = ['livestock']
  } else if (CARGO_USE_OPTIONS_BY_BODY[bodyType]) {
    allowedCommodities = CARGO_USE_OPTIONS_BY_BODY[bodyType].map((o) => o.key)
  }

  const livestockTypes =
    Array.isArray(specs.livestock_types) && specs.livestock_types.length > 0
      ? [...specs.livestock_types]
      : [...LIVESTOCK_ANIMAL_OPTIONS]

  const rawTons = Number(cfg.payload_max_tons || cfg.max_capacity || cfg.capacity_tons || 0)
  const capacityTons = rawTons > 0 ? String(rawTons) : ''
  const rawLiters = Number(specs.tank_capacity_liters || (rawTons > 0 ? Math.round(rawTons * 1000) : 0))
  const tankLiters = rawLiters > 0 ? String(rawLiters) : ''

  return {
    bodyType,
    sizeClass,
    tankerUse,
    temperatureRange,
    allowedCommodities,
    livestockTypes,
    capacityTons,
    tankLiters,
    capacityUnit: 'tons',
  }
}
