-- Remove legacy GPS Device IMEI (tracking_id) column from vehicles
ALTER TABLE public.vehicles DROP COLUMN IF EXISTS tracking_id;
