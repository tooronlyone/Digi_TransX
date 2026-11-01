-- 20261022170000_fuel_station_portal.sql
-- Complete Fuel Station Portal: pumps, pricing, dispensing point-of-sale, and logs.

CREATE TABLE IF NOT EXISTS public.fuel_station_pumps (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
    pump_number VARCHAR(100) NOT NULL,
    fuel_type VARCHAR(50) NOT NULL,
    price_per_liter NUMERIC(10, 2) NOT NULL DEFAULT 280.00,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    tank_capacity_liters NUMERIC(12, 2) NOT NULL DEFAULT 25000.00,
    current_stock_liters NUMERIC(12, 2) NOT NULL DEFAULT 15000.00,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.fuel_station_dispenses (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
    pump_id BIGINT REFERENCES public.fuel_station_pumps (id) ON DELETE SET NULL,
    vehicle_plate VARCHAR(50) NOT NULL,
    driver_name VARCHAR(150),
    driver_phone VARCHAR(50),
    fuel_type VARCHAR(50) NOT NULL,
    liters NUMERIC(10, 2) NOT NULL,
    price_per_liter NUMERIC(10, 2) NOT NULL,
    total_pkr NUMERIC(12, 2) NOT NULL,
    payment_method VARCHAR(50) NOT NULL DEFAULT 'cash',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fuel_pumps_user_id ON public.fuel_station_pumps(user_id);
CREATE INDEX IF NOT EXISTS idx_fuel_dispenses_user_id ON public.fuel_station_dispenses(user_id);
CREATE INDEX IF NOT EXISTS idx_fuel_dispenses_created_at ON public.fuel_station_dispenses(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fuel_dispenses_vehicle_plate ON public.fuel_station_dispenses(vehicle_plate);
