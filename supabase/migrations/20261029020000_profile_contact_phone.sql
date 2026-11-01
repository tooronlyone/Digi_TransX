-- Persist the separate business contact number already editable in My Account.
ALTER TABLE public.service_seeker_profiles
    ADD COLUMN IF NOT EXISTS contact_phone text;
