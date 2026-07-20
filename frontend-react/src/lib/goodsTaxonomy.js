/*
 * Goods taxonomy - frontend mirror of backend/orders/goods_taxonomy.py.
 * Keep the two in sync. Drives the cascading PostOrder form
 * (State -> [form] -> Commodity) and the adaptive measurement fields.
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

const BASE_FIELDS = {
  'solid|packaged': [F.DIMENSIONS, F.WEIGHT, F.QUANTITY],
  'solid|bulk': [F.WEIGHT, F.VOLUME_CBM],
  'liquid|': [F.VOLUME_LITERS, F.WEIGHT],
  'gas|': [F.WEIGHT, F.VOLUME_CBM],
  'livestock|': [F.ANIMAL_COUNT, F.WEIGHT],
}

const REQUIRED_FIELDS = {
  'solid|packaged': [F.DIMENSIONS, F.WEIGHT],
  'solid|bulk': [F.WEIGHT],
  'liquid|': [F.VOLUME_LITERS],
  'gas|': [F.WEIGHT],
  'livestock|': [F.ANIMAL_COUNT],
}

// commodity key -> { label, category, form, trucks[], flags{}, extraFields[] }
// trucks[] must mirror backend/orders/goods_taxonomy.py exactly.
export const GOODS_TAXONOMY = {
  // SOLID / PACKAGED
  general_cargo: { label: 'General / mixed cargo', category: 'solid', form: 'packaged', flags: {}, trucks: ['mini_pickup', 'light_truck_2_3_5_ton', 'light_truck_3_5_5_ton', 'medium_rigid_truck_5_9_ton', 'heavy_rigid_truck_9_15_ton', 'heavy_rigid_truck_15_25_ton', 'container_carrier_skeletal_trailer', 'insulated_or_dry_box_truck'] },
  cotton_textiles: { label: 'Cotton / textiles / bales', category: 'solid', form: 'packaged', flags: {}, trucks: ['medium_rigid_truck_5_9_ton', 'heavy_rigid_truck_9_15_ton', 'heavy_rigid_truck_15_25_ton', 'flatbed_trailer_open_semi_trailer', 'container_carrier_skeletal_trailer'] },
  machinery: { label: 'Machinery / heavy equipment', category: 'solid', form: 'packaged', flags: {}, trucks: ['flatbed_trailer_open_semi_trailer', 'low_bed_low_loader_trailer', 'heavy_rigid_truck_15_25_ton', 'container_carrier_skeletal_trailer'] },
  electronics: { label: 'Electronics / appliances', category: 'solid', form: 'packaged', flags: {}, trucks: ['insulated_or_dry_box_truck', 'container_carrier_skeletal_trailer', 'light_truck_3_5_5_ton', 'medium_rigid_truck_5_9_ton'] },
  furniture: { label: 'Furniture / household goods', category: 'solid', form: 'packaged', flags: {}, trucks: ['insulated_or_dry_box_truck', 'container_carrier_skeletal_trailer', 'light_truck_2_3_5_ton', 'light_truck_3_5_5_ton', 'medium_rigid_truck_5_9_ton'] },
  frozen_food: { label: 'Frozen / chilled food (meat, dairy, ice cream)', category: 'solid', form: 'packaged', flags: { refrigerated: true }, extraFields: [F.TEMPERATURE], trucks: ['refrigerated_rigid_truck', 'reefer_trailer_reefer_container_carrier'] },
  fruits_vegetables: { label: 'Fruits / vegetables (perishable)', category: 'solid', form: 'packaged', flags: { refrigerated: true }, extraFields: [F.TEMPERATURE], trucks: ['refrigerated_rigid_truck', 'reefer_trailer_reefer_container_carrier', 'insulated_or_dry_box_truck'] },
  pharmaceuticals: { label: 'Pharmaceuticals (temperature-controlled)', category: 'solid', form: 'packaged', flags: { refrigerated: true }, extraFields: [F.TEMPERATURE], trucks: ['refrigerated_rigid_truck', 'insulated_or_dry_box_truck'] },
  // SOLID / BULK
  cement: { label: 'Cement (bulk / powder)', category: 'solid', form: 'bulk', flags: {}, trucks: ['bulk_cement_tanker_powder_bulker'] },
  sand_gravel: { label: 'Sand / gravel / aggregate', category: 'solid', form: 'bulk', flags: {}, trucks: ['dump_truck_tipper'] },
  grain: { label: 'Grain / wheat / rice (bulk)', category: 'solid', form: 'bulk', flags: {}, trucks: ['dump_truck_tipper', 'bulk_cement_tanker_powder_bulker'] },
  coal_minerals: { label: 'Coal / minerals / ore', category: 'solid', form: 'bulk', flags: {}, trucks: ['dump_truck_tipper'] },
  waste: { label: 'Garbage / construction waste', category: 'solid', form: 'bulk', flags: {}, trucks: ['dump_truck_tipper'] },
  // LIQUID
  milk: { label: 'Milk / dairy liquid', category: 'liquid', form: null, flags: { food_grade: true, refrigerated: true }, extraFields: [F.TEMPERATURE], trucks: ['milk_tanker'] },
  water: { label: 'Water (potable)', category: 'liquid', form: null, flags: { food_grade: true }, trucks: ['milk_tanker'] },
  fuel: { label: 'Petrol / diesel / fuel', category: 'liquid', form: null, flags: { hazardous: true }, trucks: ['fuel_oil_tanker'] },
  edible_oil: { label: 'Edible / cooking oil', category: 'liquid', form: null, flags: { food_grade: true }, trucks: ['fuel_oil_tanker'] },
  chemicals_liquid: { label: 'Chemicals / industrial liquid', category: 'liquid', form: null, flags: { hazardous: true }, trucks: ['chemical_tanker'] },
  // GAS
  lpg_cng: { label: 'LPG / CNG / industrial gas', category: 'gas', form: null, flags: { hazardous: true }, trucks: ['chemical_tanker'] },
  // LIVESTOCK
  livestock: { label: 'Livestock (cattle, goats, sheep, poultry)', category: 'livestock', form: null, flags: {}, trucks: ['livestock_carrier'] },
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

// Cascading tree for the UI
export function buildCategoryTree() {
  const tree = {}
  for (const [key, entry] of Object.entries(GOODS_TAXONOMY)) {
    const cat = (tree[entry.category] = tree[entry.category] || { key: entry.category, label: CATEGORY_LABELS[entry.category], forms: {}, commodities: [] })
    const item = { key, label: entry.label }
    if (entry.form) {
      const fnode = (cat.forms[entry.form] = cat.forms[entry.form] || { key: entry.form, label: FORM_LABELS[entry.form] || entry.form, commodities: [] })
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
