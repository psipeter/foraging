-- The menu's progress and time left in seconds (2026-11-16): an experiment's time is its foraging time plus the time of its rankings (SessionConfig.rankingSeconds each), so the game
-- needs how far the unfinished session has got in both: `session_foraging_seconds` (the foraging clock: the logged clock less the time held in ranking breaks) and
-- `session_rankings` (the ranking breaks ended, not aborted). `session_progress` stays for older clients. Old clients ignore the new fields. No table changes.

create or replace function server.session_standing(p_run uuid) returns jsonb
language sql stable as $$
    select case when (st ->> 'completed')::boolean then jsonb_build_object('foraging_seconds', 0, 'rankings', 0)
           else jsonb_build_object(
               'foraging_seconds', greatest(0, (st ->> 'clock')::double precision - (st ->> 'held_seconds')::double precision),
               'rankings', (select count(*) from public.events where run_id = p_run and session_index = (st ->> 'session_index')::integer and type = 'rank_break_end'
                            and not coalesce((payload ->> 'aborted')::boolean, false))) end
    from (select server.resume_state(p_run) as st) q;
$$;

create or replace function server.menu(p_participant uuid, p_commit text) returns jsonb
language sql stable as $$
    select coalesce(jsonb_agg(jsonb_build_object(
        'code', e.code,
        'title', e.title,
        'n_sessions', coalesce(r.expected_sessions, re.n_sessions),
        'status', coalesce(r.status, 'none'),
        'sessions_done', coalesce((select count(*) from public.sessions s where s.run_id = r.run_id and s.completed), 0),
        'session_progress', case when r.status = 'in_progress' then server.session_progress(r.run_id) else 0 end,
        'session_foraging_seconds', case when r.status = 'in_progress' then server.session_standing(r.run_id) ->> 'foraging_seconds' else '0' end::double precision,
        'session_rankings', case when r.status = 'in_progress' then server.session_standing(r.run_id) ->> 'rankings' else '0' end::integer,
        'points', server.run_points(r.run_id),
        'unlocked', not exists (select 1 from unnest(e.requires) q
                                where not exists (select 1 from public.runs f
                                                  where f.participant_id = p_participant and f.experiment = q and f.status = 'finished'))
    ) order by e.sort_order, e.code), '[]'::jsonb)
    from public.release_experiments re
    join public.experiments e on e.code = re.experiment
    left join public.runs r on r.participant_id = p_participant and r.experiment = e.code
    where re.build_commit = p_commit;
$$;
