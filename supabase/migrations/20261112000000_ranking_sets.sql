-- The ranking Interlude (docs/DECISIONS.md, "The ranking Interlude replaces the forced-choice pair"): a set of k bushes harvested best to worst is one
-- row of interlude_trials, so the stream, its sequence numbers, the gap check, the resume tally and the points sums (all over `bonus`) work unchanged.
-- Columns are only appended (nullable); the pair columns (left_*, right_*, correct_side, choice, choice_correct, ...) are empty in a set's row.
--   set_size       bushes in the set
--   correct_pairs  implied pairs ordered correctly (picked above picked in the order picked, picked above unpicked), ties (below the file's tolerance) not counted
--   total_pairs    the implied pairs counted
--   bushes         jsonb array, one object per bush in slot order: id, slot, shape, color, moisture, value (true reward per fruit), rank (null if not finished),
--                  start_time and finish_time (set clock, seconds; null if never started or finished), fruits (taken from it)
alter table public.interlude_trials
    add column set_size      integer,
    add column correct_pairs integer,
    add column total_pairs   integer,
    add column bushes        jsonb;

-- The long form: one row per bush of each set (the table stays deny-all; the view is read with the owner's rights only).
create view public.interlude_picks with (security_invoker = true) as
select t.run_id, t.session_index, t.seq, t.presented_order, t.trial_index, t.set_size,
       (b ->> 'id')::integer              as bush_id,
       (b ->> 'slot')::integer            as slot,
       (b ->> 'shape')::double precision  as shape,
       (b ->> 'color')::double precision  as color,
       (b ->> 'moisture')::double precision as moisture,
       (b ->> 'value')::double precision  as value,
       (b ->> 'rank')::integer            as rank,
       (b ->> 'start_time')::double precision  as start_time,
       (b ->> 'finish_time')::double precision as finish_time,
       (b ->> 'fruits')::integer          as fruits
from public.interlude_trials t, jsonb_array_elements(t.bushes) b
where t.bushes is not null;
revoke all on public.interlude_picks from public, anon, authenticated;
