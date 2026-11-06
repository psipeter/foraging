-- The menu shows the points a participant has earned in each experiment (and a total): the score of the experiment's completed sessions plus the
-- bonus of its Interlude trials, practice sessions and practice Interludes left out (they pay nothing), as the game adds them up for its own final screen.
create or replace function server.menu(p_participant uuid, p_commit text) returns jsonb
language sql stable as $$
    select coalesce(jsonb_agg(jsonb_build_object(
        'code', e.code,
        'title', e.title,
        'n_sessions', re.n_sessions,
        'status', coalesce(r.status, 'none'),
        'sessions_done', coalesce((select count(*) from public.sessions s where s.run_id = r.run_id and s.completed), 0),
        'points', coalesce((select sum(s.final_score) from public.sessions s
                            where s.run_id = r.run_id and s.completed and not s.is_interlude and not s.is_practice), 0)
                + coalesce((select sum(coalesce(t.bonus, 0)) from public.interlude_trials t
                            join public.sessions s on s.run_id = t.run_id and s.session_index = t.session_index
                            where t.run_id = r.run_id and s.completed and s.is_interlude and not s.is_practice), 0),
        'unlocked', not exists (select 1 from unnest(e.requires) q
                                where not exists (select 1 from public.runs f
                                                  where f.participant_id = p_participant and f.experiment = q and f.status = 'finished'))
    ) order by e.sort_order, e.code), '[]'::jsonb)
    from public.release_experiments re
    join public.experiments e on e.code = re.experiment
    left join public.runs r on r.participant_id = p_participant and r.experiment = e.code
    where re.build_commit = p_commit;
$$;
