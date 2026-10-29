-- Real seconds the game was held still (mouse released, upload gate, ...) while an Interlude trial was live: the trial clock stops
-- during them, so a participant could pause to think; analyses can exclude or flag such trials. Added at the end of the table.
alter table public.interlude_trials add column paused_seconds double precision;
