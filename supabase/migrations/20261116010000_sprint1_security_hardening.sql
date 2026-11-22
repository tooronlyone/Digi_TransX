-- Sprint 1 Security Remediation (V1-SEC-002 & V1-SEC-004)
-- 1. Track explicit OTP supersession on public.password_reset_otps
-- 2. Add durable PostgreSQL rate-limiting table with strict RLS (backend service_role only)

BEGIN;

ALTER TABLE public.password_reset_otps
    ADD COLUMN IF NOT EXISTS superseded_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_password_reset_otps_lookup
    ON public.password_reset_otps (user_id, purpose, id DESC);

CREATE TABLE IF NOT EXISTS public.http_rate_limits (
    bucket_key    text NOT NULL,
    window_start  timestamptz NOT NULL,
    request_count integer NOT NULL DEFAULT 0 CHECK (request_count >= 0),
    expires_at    timestamptz NOT NULL,
    PRIMARY KEY (bucket_key, window_start)
);

CREATE INDEX IF NOT EXISTS idx_http_rate_limits_expires_at
    ON public.http_rate_limits (expires_at);

ALTER TABLE public.http_rate_limits ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.http_rate_limits FROM PUBLIC, anon, authenticated;

DROP POLICY IF EXISTS backend_only ON public.http_rate_limits;
CREATE POLICY backend_only ON public.http_rate_limits
    FOR ALL TO service_role USING (true) WITH CHECK (true);

COMMENT ON TABLE public.http_rate_limits IS
    'Shared PostgreSQL fixed-window HTTP rate limiter buckets for multi-worker V1 enforcement.';

COMMIT;
