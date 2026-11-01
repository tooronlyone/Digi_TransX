-- Migration for Driver Role, Verification, GPS Tracking, Reputation, and Trip Assignments

CREATE TABLE IF NOT EXISTS driver_profiles (
    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    unique_driver_id VARCHAR(32) UNIQUE NOT NULL,
    license_number VARCHAR(64) NOT NULL,
    license_expiry DATE,
    experience_years INT DEFAULT 1,
    rating NUMERIC(3, 2) DEFAULT 5.00,
    rating_count INT DEFAULT 0,
    total_trips INT DEFAULT 0,
    verified_status VARCHAR(32) DEFAULT 'verified',
    employment_type VARCHAR(32) DEFAULT 'per_trip', -- 'per_trip' or 'permanent'
    current_truck_id BIGINT REFERENCES vehicles(id) ON DELETE SET NULL,
    is_available BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_driver_profiles_unique_id ON driver_profiles(unique_driver_id);
CREATE INDEX IF NOT EXISTS idx_driver_profiles_current_truck ON driver_profiles(current_truck_id);

-- Driver Incidents / Theft & Misconduct Log
CREATE TABLE IF NOT EXISTS driver_incidents (
    id BIGSERIAL PRIMARY KEY,
    driver_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reporter_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trip_id BIGINT REFERENCES shipment_trips(id) ON DELETE SET NULL,
    agreement_trip_id BIGINT REFERENCES agreement_trips(id) ON DELETE SET NULL,
    incident_type VARCHAR(64) NOT NULL, -- 'theft', 'damage', 'misconduct', 'delay', 'other'
    severity VARCHAR(32) DEFAULT 'medium', -- 'low', 'medium', 'high', 'critical'
    description TEXT NOT NULL,
    evidence_urls JSONB DEFAULT '[]'::jsonb,
    status VARCHAR(32) DEFAULT 'investigating', -- 'investigating', 'confirmed', 'dismissed'
    rating_penalty NUMERIC(3, 2) DEFAULT 0.00,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_driver_incidents_driver ON driver_incidents(driver_user_id);

-- Driver Reviews & Ratings
CREATE TABLE IF NOT EXISTS driver_reviews (
    id BIGSERIAL PRIMARY KEY,
    driver_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reviewer_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trip_id BIGINT REFERENCES shipment_trips(id) ON DELETE SET NULL,
    agreement_trip_id BIGINT REFERENCES agreement_trips(id) ON DELETE SET NULL,
    rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_driver_reviews_driver ON driver_reviews(driver_user_id);

-- Driver Trip Dispatch Requests & Assignments
CREATE TABLE IF NOT EXISTS driver_trip_assignments (
    id BIGSERIAL PRIMARY KEY,
    driver_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    transporter_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    truck_id BIGINT NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    trip_type VARCHAR(32) NOT NULL DEFAULT 'one_time', -- 'one_time' or 'agreement'
    trip_id BIGINT REFERENCES shipment_trips(id) ON DELETE SET NULL,
    agreement_trip_id BIGINT REFERENCES agreement_trips(id) ON DELETE SET NULL,
    offer_amount NUMERIC(12, 2) DEFAULT 0.00,
    notes TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'requested', -- 'requested', 'accepted', 'rejected', 'in_progress', 'completed', 'cancelled'
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_driver_assignments_driver ON driver_trip_assignments(driver_user_id);
CREATE INDEX IF NOT EXISTS idx_driver_assignments_transporter ON driver_trip_assignments(transporter_user_id);

-- Realtime Driver GPS Location Ping Log
CREATE TABLE IF NOT EXISTS driver_gps_pings (
    id BIGSERIAL PRIMARY KEY,
    driver_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    truck_id BIGINT REFERENCES vehicles(id) ON DELETE SET NULL,
    trip_id BIGINT REFERENCES shipment_trips(id) ON DELETE SET NULL,
    agreement_trip_id BIGINT REFERENCES agreement_trips(id) ON DELETE SET NULL,
    lat NUMERIC(10, 7) NOT NULL,
    lng NUMERIC(10, 7) NOT NULL,
    speed_kmh NUMERIC(6, 2) DEFAULT 0.00,
    heading NUMERIC(5, 2) DEFAULT 0.00,
    altitude NUMERIC(8, 2),
    battery_level INT,
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_driver_gps_driver_recent ON driver_gps_pings(driver_user_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_driver_gps_truck_recent ON driver_gps_pings(truck_id, recorded_at DESC);
