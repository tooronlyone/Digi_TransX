-- Migration for Driver Fuel Expense & Consumption Logs

CREATE TABLE IF NOT EXISTS public.driver_fuel_logs (
    id BIGSERIAL PRIMARY KEY,
    driver_user_id BIGINT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    truck_id BIGINT REFERENCES public.vehicles(id) ON DELETE SET NULL,
    assignment_id BIGINT REFERENCES public.driver_trip_assignments(id) ON DELETE SET NULL,
    trip_id BIGINT REFERENCES public.shipment_trips(id) ON DELETE SET NULL,
    agreement_trip_id BIGINT REFERENCES public.agreement_trips(id) ON DELETE SET NULL,
    pump_station_id BIGINT REFERENCES public.users(id) ON DELETE SET NULL,
    pump_name VARCHAR(150) NOT NULL,
    pump_brand VARCHAR(50) DEFAULT 'Other', -- 'PSO', 'Shell', 'TotalParco', 'Attock', 'Hascol', 'Gas & Go', 'Other'
    city VARCHAR(100) NOT NULL,
    area_landmark VARCHAR(150),
    pump_location_lat NUMERIC(10, 7),
    pump_location_lng NUMERIC(10, 7),
    fuel_type VARCHAR(50) NOT NULL DEFAULT 'diesel', -- 'diesel', 'petrol', 'cng'
    liters NUMERIC(10, 2) NOT NULL,
    price_per_liter NUMERIC(10, 2) NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL,
    payment_mode VARCHAR(50) NOT NULL DEFAULT 'cash', -- 'cash', 'driver_wallet', 'transporter_account', 'company_card'
    odometer_km NUMERIC(12, 2),
    trip_distance_km NUMERIC(10, 2),
    fuel_average_km_per_liter NUMERIC(6, 2),
    receipt_image_url TEXT,
    notes TEXT,
    fuel_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_driver_fuel_driver ON public.driver_fuel_logs(driver_user_id);
CREATE INDEX IF NOT EXISTS idx_driver_fuel_trip ON public.driver_fuel_logs(trip_id);
CREATE INDEX IF NOT EXISTS idx_driver_fuel_assignment ON public.driver_fuel_logs(assignment_id);
CREATE INDEX IF NOT EXISTS idx_driver_fuel_date ON public.driver_fuel_logs(fuel_date DESC);
