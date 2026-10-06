-- EXPAND phase: additive only. Old code never selects this column and
-- keeps working; new code treats NULL as "venue unknown". The CONTRACT
-- phase (making it NOT NULL, dropping old paths) waits until no old
-- deployment remains.
ALTER TABLE events ADD COLUMN venue TEXT;
