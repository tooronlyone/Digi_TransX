-- A driver has no earned rating until at least one genuine review exists.
ALTER TABLE public.driver_profiles
    ALTER COLUMN rating DROP DEFAULT;

UPDATE public.driver_profiles
SET rating = NULL,
    updated_at = NOW()
WHERE COALESCE(rating_count, 0) = 0;

