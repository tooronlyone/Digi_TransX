-- After the rollout preflight reports no violating legacy balances, validate
-- every existing wallet against the same backstop already enforced on writes.
-- A violating row aborts this migration; no balance is silently repaired.
-- Replay is safe: VALIDATE is a no-op for an already validated constraint.
ALTER TABLE public.wallets VALIDATE CONSTRAINT wallets_money_invariants;
