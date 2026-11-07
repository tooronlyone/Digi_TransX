/*
 * Goods taxonomy - frontend mirror of backend/orders/goods_taxonomy.py.
 * Keep the two in sync. Drives the Smart 3-Step Client PostOrder form
 * and the adaptive measurement fields.
 */

// Field ids
export const F = {
  DIMENSIONS: 'dimensions',
  WEIGHT: 'weight',
  VOLUME_CBM: 'volume_cbm',
  VOLUME_LITERS: 'volume_liters',
  QUANTITY: 'quantity',
  ANIMAL_COUNT: 'animal_count',
  TEMPERATURE: 'temperature',
}

export const MIN_ORDER_TONS = 0.3
export const MAX_ORDER_TONS = 100
export const MIN_ORDER_LITERS = 300
export const MAX_ORDER_LITERS = 100000
export const FT_TO_CM = 30.48

const BASE_FIELDS = {
  'solid|packaged': [F.DIMENSIONS, F.WEIGHT, F.QUANTITY],
  'solid|bulk': [F.WEIGHT, F.VOLUME_CBM],
  'liquid|': [F.VOLUME_LITERS, F.WEIGHT],
  'gas|': [F.WEIGHT, F.VOLUME_CBM],
  'livestock|': [F.ANIMAL_COUNT, F.WEIGHT],
}

const REQUIRED_FIELDS = {
  'solid|packaged': [F.WEIGHT],
  'solid|bulk': [F.WEIGHT],
  'liquid|': [F.VOLUME_LITERS],
  'gas|': [F.WEIGHT],
  'livestock|': [F.ANIMAL_COUNT],
}

// commodity key -> { label, category, form, trucks[], flags{}, extraFields[] }
// trucks[] must mirror backend/orders/goods_taxonomy.py exactly.
export const GOODS_TAXONOMY = {
  // SOLID / PACKAGED
  general_cargo: {
    label: 'General / mixed cargo',
    category: 'solid',
    form: 'packaged',
    flags: {},
    trucks: [
      'mini_pickup',
      'light_truck_2_3_5_ton',
      'light_truck_3_5_5_ton',
      'medium_rigid_truck_5_9_ton',
      'heavy_rigid_truck_9_15_ton',
      'heavy_rigid_truck_15_25_ton',
      'container_carrier_skeletal_trailer',
      'insulated_or_dry_box_truck',
    ],
  },
  cotton_textiles: {
    label: 'Cotton / textiles / bales',
    category: 'solid',
    form: 'packaged',
    flags: {},
    trucks: [
      'medium_rigid_truck_5_9_ton',
      'heavy_rigid_truck_9_15_ton',
      'heavy_rigid_truck_15_25_ton',
      'flatbed_trailer_open_semi_trailer',
      'container_carrier_skeletal_trailer',
    ],
  },
  machinery: {
    label: 'Machinery / heavy equipment',
    category: 'solid',
    form: 'packaged',
    flags: {},
    trucks: [
      'flatbed_trailer_open_semi_trailer',
      'low_bed_low_loader_trailer',
      'heavy_rigid_truck_15_25_ton',
      'container_carrier_skeletal_trailer',
    ],
  },
  construction_steel: {
    label: 'Steel / sariya / pipes / girders',
    category: 'solid',
    form: 'packaged',
    flags: {},
    trucks: [
      'light_truck_3_5_5_ton',
      'medium_rigid_truck_5_9_ton',
      'heavy_rigid_truck_9_15_ton',
      'heavy_rigid_truck_15_25_ton',
      'flatbed_trailer_open_semi_trailer',
      'low_bed_low_loader_trailer',
    ],
  },
  cement_bags: {
    label: 'Cement / fertilizer / grain bags (boriyan)',
    category: 'solid',
    form: 'packaged',
    flags: {},
    trucks: [
      'mini_pickup',
      'light_truck_2_3_5_ton',
      'light_truck_3_5_5_ton',
      'medium_rigid_truck_5_9_ton',
      'heavy_rigid_truck_9_15_ton',
      'heavy_rigid_truck_15_25_ton',
      'flatbed_trailer_open_semi_trailer',
      'container_carrier_skeletal_trailer',
      'insulated_or_dry_box_truck',
    ],
  },
  electronics: {
    label: 'Electronics / appliances',
    category: 'solid',
    form: 'packaged',
    flags: {},
    trucks: [
      'insulated_or_dry_box_truck',
      'container_carrier_skeletal_trailer',
      'light_truck_3_5_5_ton',
      'medium_rigid_truck_5_9_ton',
    ],
  },
  furniture: {
    label: 'Furniture / household goods',
    category: 'solid',
    form: 'packaged',
    flags: {},
    trucks: [
      'insulated_or_dry_box_truck',
      'container_carrier_skeletal_trailer',
      'light_truck_2_3_5_ton',
      'light_truck_3_5_5_ton',
      'medium_rigid_truck_5_9_ton',
    ],
  },
  frozen_food: {
    label: 'Frozen / chilled food (meat, dairy, ice cream)',
    category: 'solid',
    form: 'packaged',
    flags: { refrigerated: true },
    extraFields: [F.TEMPERATURE],
    trucks: ['refrigerated_rigid_truck', 'reefer_trailer_reefer_container_carrier'],
  },
  fruits_vegetables: {
    label: 'Fruits / vegetables (perishable)',
    category: 'solid',
    form: 'packaged',
    flags: { refrigerated: true },
    extraFields: [F.TEMPERATURE],
    trucks: [
      'refrigerated_rigid_truck',
      'reefer_trailer_reefer_container_carrier',
      'insulated_or_dry_box_truck',
    ],
  },
  pharmaceuticals: {
    label: 'Pharmaceuticals (temperature-controlled)',
    category: 'solid',
    form: 'packaged',
    flags: { refrigerated: true },
    extraFields: [F.TEMPERATURE],
    trucks: ['refrigerated_rigid_truck', 'insulated_or_dry_box_truck'],
  },
  // SOLID / BULK
  cement: {
    label: 'Cement (bulk / powder)',
    category: 'solid',
    form: 'bulk',
    flags: {},
    trucks: ['bulk_cement_tanker_powder_bulker'],
  },
  sand_gravel: {
    label: 'Sand / gravel / aggregate',
    category: 'solid',
    form: 'bulk',
    flags: {},
    trucks: ['dump_truck_tipper'],
  },
  grain: {
    label: 'Grain / wheat / rice (bulk)',
    category: 'solid',
    form: 'bulk',
    flags: {},
    trucks: ['dump_truck_tipper', 'bulk_cement_tanker_powder_bulker'],
  },
  coal_minerals: {
    label: 'Coal / minerals / ore',
    category: 'solid',
    form: 'bulk',
    flags: {},
    trucks: ['dump_truck_tipper'],
  },
  waste: {
    label: 'Garbage / construction waste',
    category: 'solid',
    form: 'bulk',
    flags: {},
    trucks: ['dump_truck_tipper'],
  },
  // LIQUID
  milk: {
    label: 'Milk / dairy liquid',
    category: 'liquid',
    form: null,
    flags: { food_grade: true, refrigerated: true },
    extraFields: [F.TEMPERATURE],
    trucks: ['milk_tanker'],
  },
  water: {
    label: 'Water (potable)',
    category: 'liquid',
    form: null,
    flags: { food_grade: true },
    trucks: ['milk_tanker'],
  },
  fuel: {
    label: 'Petrol / diesel / fuel',
    category: 'liquid',
    form: null,
    flags: { hazardous: true },
    trucks: ['fuel_oil_tanker'],
  },
  edible_oil: {
    label: 'Edible / cooking oil',
    category: 'liquid',
    form: null,
    flags: { food_grade: true },
    trucks: ['fuel_oil_tanker'],
  },
  chemicals_liquid: {
    label: 'Chemicals / industrial liquid',
    category: 'liquid',
    form: null,
    flags: { hazardous: true },
    trucks: ['chemical_tanker'],
  },
  // GAS
  lpg_cng: {
    label: 'LPG / CNG / industrial gas',
    category: 'gas',
    form: null,
    flags: { hazardous: true },
    trucks: ['chemical_tanker'],
  },
  // LIVESTOCK
  livestock: {
    label: 'Livestock (cattle, goats, sheep, poultry)',
    category: 'livestock',
    form: null,
    flags: {},
    trucks: ['livestock_carrier'],
  },
}

/**
 * 6 Human-Friendly Client Goods Groups (mirrors Transporter's Hybrid Body & Cargo model).
 */
export const CLIENT_GOODS_GROUPS = [
  {
    key: 'general_shifting',
    title: 'General Cargo, Cartons & Shifting',
    subtitle: 'Home/office furniture, commercial cartons, textiles, garments & appliances',
    icon: 'fa-boxes-stacked',
    commodities: [
      {
        key: 'general_cargo',
        title: 'General Cargo / Commercial Cartons',
        desc: 'FMCG boxes, pallets, shop goods & general packaged freight',
        defaultTons: '3.5',
      },
      {
        key: 'furniture',
        title: 'Furniture & Home / Office Shifting',
        desc: 'Beds, sofas, cupboards, office tables & household luggage',
        defaultTons: '3',
      },
      {
        key: 'cotton_textiles',
        title: 'Cotton / Textiles / Cloth Bales',
        desc: 'Textile rolls, cotton bales, yarn & garment cartons',
        defaultTons: '8',
      },
      {
        key: 'electronics',
        title: 'Electronics & Home Appliances',
        desc: 'Fridges, ACs, TVs, solar panels & fragile boxed goods',
        defaultTons: '3.5',
      },
    ],
  },
  {
    key: 'construction_industrial',
    title: 'Construction, Bags & Heavy Industrial',
    subtitle: 'Cement/fertilizer bags (boriyan), steel (sariya), pipes & heavy machinery',
    icon: 'fa-helmet-safety',
    commodities: [
      {
        key: 'cement_bags',
        title: 'Cement / Fertilizer / Grain Bags (Boriyan)',
        desc: '50kg cement bags, urea/khaad bags or wheat sacks on open/flatbed trucks',
        defaultTons: '15',
      },
      {
        key: 'construction_steel',
        title: 'Steel / Sariya / Iron Pipes / Girders',
        desc: 'Long steel bars, iron sheets, scaffolding & structural pipes',
        defaultTons: '15',
        suggestLengthFt: true,
      },
      {
        key: 'machinery',
        title: 'Heavy Machinery, Generators & Containers',
        desc: 'Industrial machines, transformers, excavators & 20ft/40ft containers',
        defaultTons: '25',
        suggestLengthFt: true,
      },
    ],
  },
  {
    key: 'dumper_bulk',
    title: 'Loose Dumper / Bulk Material',
    subtitle: 'Sand (rait), gravel (bajri), crush, loose grain, coal & bulk cement silo',
    icon: 'fa-truck-monster',
    commodities: [
      {
        key: 'sand_gravel',
        title: 'Sand / Gravel / Crush (Rait, Bajri, Pathar)',
        desc: 'Loose construction aggregate for hydraulic dumper / tipper trucks',
        defaultTons: '20',
      },
      {
        key: 'grain',
        title: 'Loose Bulk Grain / Wheat / Rice',
        desc: 'Unbagged bulk agricultural grain in tipper or grain bulker',
        defaultTons: '18',
      },
      {
        key: 'coal_minerals',
        title: 'Coal / Minerals / Stone Ore',
        desc: 'Loose coal, gypsum, limestone or mining ore (Dumper)',
        defaultTons: '22',
      },
      {
        key: 'cement',
        title: 'Loose Cement Powder (Pneumatic Silo Bulker Only)',
        desc: 'Unbagged dry cement/fly-ash powder requiring a sealed pneumatic bulker',
        defaultTons: '30',
      },
      {
        key: 'waste',
        title: 'Construction Debris / Earthmoving',
        desc: 'Excavated soil, rubble or site clearance waste (Dumper)',
        defaultTons: '15',
      },
    ],
  },
  {
    key: 'cold_chain',
    title: 'Cold Chain, Fruits & Medicines',
    subtitle: 'Frozen meat/ice cream (-18°C), chilled dairy/pharma (0–8°C) & fresh mandi produce',
    icon: 'fa-snowflake',
    commodities: [
      {
        key: 'fruits_vegetables',
        title: 'Fresh Fruits & Vegetables (Mandi / Chilled)',
        desc: 'Potatoes, onions, mangoes, apples, kinnow & fresh produce',
        defaultTons: '5',
      },
      {
        key: 'frozen_food',
        title: 'Frozen Meat, Poultry, Ice Cream & Dairy',
        desc: 'Temperature-controlled deep frozen (-18°C) or chilled food',
        defaultTons: '8',
      },
      {
        key: 'pharmaceuticals',
        title: 'Pharmaceuticals & Medical Supplies',
        desc: 'Insulated or chilled (2°C to 8°C) medicines & vaccines',
        defaultTons: '4',
      },
    ],
  },
  {
    key: 'liquid_gas_tanker',
    title: 'Liquid & Gas Tanker Loads',
    subtitle: 'Dedicated food-grade milk/water/oil tankers, fuel bowzers & chemical/LPG tankers',
    icon: 'fa-fill-drip',
    commodities: [
      {
        key: 'milk',
        title: 'Milk / Fresh Dairy Liquid',
        desc: 'Food-grade stainless-steel insulated dairy tanker',
        defaultTons: '12',
        supportsLiters: true,
      },
      {
        key: 'water',
        title: 'Sweet / Potable Drinking Water',
        desc: 'Clean water bowzer / food-grade water tanker',
        defaultTons: '12',
        supportsLiters: true,
      },
      {
        key: 'edible_oil',
        title: 'Edible / Cooking Oil / Ghee Liquid',
        desc: 'Dedicated food-grade edible oil tanker (never used for fuel)',
        defaultTons: '15',
        supportsLiters: true,
      },
      {
        key: 'fuel',
        title: 'Petrol / Diesel / Furnace Oil',
        desc: 'Hazmat-certified petroleum fuel tanker',
        defaultTons: '25',
        supportsLiters: true,
      },
      {
        key: 'chemicals_liquid',
        title: 'Industrial Liquid Chemicals / Acids',
        desc: 'Hazmat chemical tanker for industrial liquids',
        defaultTons: '20',
        supportsLiters: true,
      },
      {
        key: 'lpg_cng',
        title: 'LPG / CNG / Industrial Gas',
        desc: 'Pressurized gas bowzer (measured in Tons)',
        defaultTons: '20',
        supportsLiters: false,
      },
    ],
  },
  {
    key: 'livestock_group',
    title: 'Livestock / Maweshi (Animals)',
    subtitle: 'Ventilated livestock carrier for cattle, buffalo, goats, sheep & poultry',
    icon: 'fa-cow',
    commodities: [
      {
        key: 'livestock',
        title: 'Livestock (Cattle, Buffalo, Goats, Sheep, Poultry)',
        desc: 'Safe ventilated animal carrier matched by head count & total weight',
        defaultTons: '5',
      },
    ],
  },
]

export const WEIGHT_QUICK_PRESETS = [
  { tons: '1', label: '~1 Ton (Suzuki / Mini Pickup)' },
  { tons: '3', label: '~3 Tons (Shehzore 10ft)' },
  { tons: '5', label: '~5 Tons (Mazda 16ft)' },
  { tons: '9', label: '~9 Tons (Large Mazda 19ft)' },
  { tons: '15', label: '~15 Tons (6-Wheeler Hino)' },
  { tons: '25', label: '~25 Tons (10-Wheeler)' },
  { tons: '35', label: '~35 Tons (40ft Trailer)' },
]

export const LIQUID_QUICK_PRESETS = [
  { tons: '5', liters: '5000', label: '5 Tons (5,000 L)' },
  { tons: '12', liters: '12000', label: '12 Tons (12,000 L)' },
  { tons: '15', liters: '15000', label: '15 Tons (15,000 L)' },
  { tons: '25', liters: '25000', label: '25 Tons (25,000 L)' },
  { tons: '40', liters: '40000', label: '40 Tons (40,000 L)' },
]

export const LENGTH_FEET_PRESETS = [
  { ft: '', label: 'Standard Load (Fits normal truck bed)' },
  { ft: '10', label: 'Up to 10 ft (Shehzore or bigger)' },
  { ft: '16', label: 'Up to 16 ft (Mazda or bigger)' },
  { ft: '20', label: '20 ft (Sariya / 20ft Container / Heavy Rigid)' },
  { ft: '26', label: '26 ft (10-Wheeler or 40ft Trailer)' },
  { ft: '40', label: '40 ft (Full 40ft Flatbed / Container Trailer)' },
]

export const TEMPERATURE_PRESETS = [
  { value: '4', label: 'Chilled (0°C to +8°C)', desc: 'Fresh fruits, vegetables, dairy & medicines' },
  { value: '-18', label: 'Deep Frozen (-18°C)', desc: 'Frozen meat, poultry, fish & ice cream' },
  { value: '', label: 'Normal / Non-AC (Ambient)', desc: 'No refrigeration required' },
]

export const LIVESTOCK_PRESETS = [
  { key: 'Cattle', label: 'Cattle / Buffalo (Gaye / Bhains)', avgTonsPerHead: 0.45 },
  { key: 'Goats', label: 'Goats / Sheep (Bakri / Dumba)', avgTonsPerHead: 0.05 },
  { key: 'Poultry', label: 'Poultry Crates (Murghi)', avgTonsPerHead: 0.025 },
]

const PROVINCE_KEYWORDS = [
  ['islamabad', 'Islamabad Capital Territory'],
  ['punjab', 'Punjab'],
  ['sindh', 'Sindh'],
  ['khyber pakhtunkhwa', 'Khyber Pakhtunkhwa'],
  ['kpk', 'Khyber Pakhtunkhwa'],
  ['balochistan', 'Balochistan'],
  ['baluchistan', 'Balochistan'],
  ['gilgit', 'Gilgit-Baltistan'],
  ['skardu', 'Gilgit-Baltistan'],
  ['hunza', 'Gilgit-Baltistan'],
  ['azad jammu', 'Azad Jammu and Kashmir'],
  ['azad kashmir', 'Azad Jammu and Kashmir'],
  ['muzaffarabad', 'Azad Jammu and Kashmir'],
  ['mirpur', 'Azad Jammu and Kashmir'],
  // Major cities
  ['lahore', 'Punjab'],
  ['gujranwala', 'Punjab'],
  ['faisalabad', 'Punjab'],
  ['rawalpindi', 'Punjab'],
  ['multan', 'Punjab'],
  ['sialkot', 'Punjab'],
  ['gujrat', 'Punjab'],
  ['sargodha', 'Punjab'],
  ['bahawalpur', 'Punjab'],
  ['sheikhupura', 'Punjab'],
  ['kasur', 'Punjab'],
  ['sahiwal', 'Punjab'],
  ['okara', 'Punjab'],
  ['jhelum', 'Punjab'],
  ['rahim yar khan', 'Punjab'],
  ['karachi', 'Sindh'],
  ['hyderabad', 'Sindh'],
  ['sukkur', 'Sindh'],
  ['larkana', 'Sindh'],
  ['nawabshah', 'Sindh'],
  ['thatta', 'Sindh'],
  ['peshawar', 'Khyber Pakhtunkhwa'],
  ['mardan', 'Khyber Pakhtunkhwa'],
  ['abbottabad', 'Khyber Pakhtunkhwa'],
  ['swat', 'Khyber Pakhtunkhwa'],
  ['mingora', 'Khyber Pakhtunkhwa'],
  ['kohat', 'Khyber Pakhtunkhwa'],
  ['nowshera', 'Khyber Pakhtunkhwa'],
  ['haripur', 'Khyber Pakhtunkhwa'],
  ['mansehra', 'Khyber Pakhtunkhwa'],
  ['quetta', 'Balochistan'],
  ['gwadar', 'Balochistan'],
  ['khuzdar', 'Balochistan'],
  ['chaman', 'Balochistan'],
  ['turbat', 'Balochistan'],
  ['hub', 'Balochistan'],
]

export function inferPakistanProvince(locationText) {
  if (!locationText) return null
  const norm = String(locationText).toLowerCase()
  for (const [token, province] of PROVINCE_KEYWORDS) {
    if (norm.includes(token)) return province
  }
  return null
}

export function findGroupForCommodity(commodityKey) {
  if (!commodityKey) return ''
  const found = CLIENT_GOODS_GROUPS.find((g) => g.commodities.some((c) => c.key === commodityKey))
  return found ? found.key : ''
}

export function supportsLitersForCommodity(commodityKey) {
  return ['milk', 'water', 'edible_oil', 'fuel', 'chemicals_liquid'].includes(commodityKey)
}

const CATEGORY_LABELS = { solid: 'Solid', liquid: 'Liquid', gas: 'Gas', livestock: 'Livestock' }
const FORM_LABELS = { packaged: 'Packaged / unit', bulk: 'Bulk / loose' }
const CATEGORY_ORDER = ['solid', 'liquid', 'gas', 'livestock']

export function getCommodity(key) {
  return GOODS_TAXONOMY[key] || null
}

export function fieldsFor(key) {
  const entry = getCommodity(key)
  if (!entry) return [F.WEIGHT]
  const base = [...(BASE_FIELDS[`${entry.category}|${entry.form || ''}`] || [F.WEIGHT])]
  for (const f of entry.extraFields || []) if (!base.includes(f)) base.push(f)
  return base
}

export function requiredFieldsFor(key) {
  const entry = getCommodity(key)
  if (!entry) return [F.WEIGHT]
  return REQUIRED_FIELDS[`${entry.category}|${entry.form || ''}`] || [F.WEIGHT]
}

export function flagsFor(key) {
  const entry = getCommodity(key)
  return { refrigerated: false, hazardous: false, food_grade: false, ...(entry ? entry.flags : {}) }
}

// Cascading tree for backward compatibility
export function buildCategoryTree() {
  const tree = {}
  for (const [key, entry] of Object.entries(GOODS_TAXONOMY)) {
    const cat = (tree[entry.category] = tree[entry.category] || {
      key: entry.category,
      label: CATEGORY_LABELS[entry.category],
      forms: {},
      commodities: [],
    })
    const item = { key, label: entry.label }
    if (entry.form) {
      const fnode = (cat.forms[entry.form] = cat.forms[entry.form] || {
        key: entry.form,
        label: FORM_LABELS[entry.form] || entry.form,
        commodities: [],
      })
      fnode.commodities.push(item)
    } else {
      cat.commodities.push(item)
    }
  }
  return CATEGORY_ORDER.filter((c) => tree[c]).map((c) => ({
    key: tree[c].key,
    label: tree[c].label,
    forms: Object.values(tree[c].forms),
    commodities: tree[c].commodities,
  }))
}

export const CATEGORY_TREE = buildCategoryTree()
