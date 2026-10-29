-- Online data collection schema (docs/ONLINE_DATA_PLAN.md, section 1; rationale in docs/DECISIONS.md).
-- Every table is deny-all for the public roles: only Edge Functions (service role) read or write.
-- `seq` is a per-session, per-stream counter assigned by the client; the primary keys make every upload idempotent.
-- 0/1 flags are smallint, as in the CSV mirror the client writes locally (events, interlude_trials).

create table public.runs (
    run_id        uuid primary key default gen_random_uuid(),
    token_hash    text not null,
    platform      text,
    build_commit  text,                 -- the build the run started on
    build_commits text[] not null default '{}',   -- every build commit that played any part of it (a resume may be on a newer build)
    build_dirty   boolean,
    unity_version text,
    status        text not null default 'in_progress' check (status in ('in_progress', 'finished', 'terminated')),
    started_at    timestamptz not null default now(),
    finished_at   timestamptz
);

-- The Prolific ID lives only here, apart from every analysis table.
create table public.pid_registry (
    prolific_pid text primary key,
    run_id       uuid not null unique references public.runs (run_id) on delete cascade
);

create table public.sessions (
    run_id           uuid not null references public.runs (run_id) on delete cascade,
    session_index    integer not null check (session_index >= 0),
    name             text not null,
    is_practice      boolean not null default false,
    is_interlude     boolean not null default false,
    world_seed       integer,
    world_file       text,
    world_sha256     text,
    interlude_file   text,
    interlude_sha256 text,
    config           jsonb not null,      -- the full SessionConfig
    camera           jsonb,               -- fieldOfView, nearClipPlane, farClipPlane, localHeight
    display          jsonb,
    frame_stats      jsonb,
    started_at       timestamptz,
    ended_at         timestamptz,
    completed        boolean not null default false,
    final_score      double precision,
    primary key (run_id, session_index)
);

create table public.events (
    run_id        uuid not null,
    session_index integer not null,
    seq           integer not null check (seq >= 0),
    t             double precision not null,   -- unpaused session seconds
    real          double precision,            -- seconds since the logger started
    type          text not null,
    tree_id       integer,
    k             integer,
    reward        double precision,
    running_total double precision,
    payload       jsonb,
    primary key (run_id, session_index, seq),
    foreign key (run_id, session_index) references public.sessions (run_id, session_index) on delete cascade
);

-- One row per chunk of consecutive frames (scripts/trajectory_codec.py); seq of a frame = first_seq + its index in the chunk.
create table public.trajectory (
    run_id        uuid not null,
    session_index integer not null,
    first_seq     integer not null check (first_seq >= 0),
    n_frames      integer not null check (n_frames > 0),
    t_start       double precision not null,
    t_end         double precision not null,
    last_frame    jsonb not null,       -- t, x, z, yaw, pitch, keys of the chunk's last frame (the resume pose)
    data          bytea not null,
    primary key (run_id, session_index, first_seq),
    foreign key (run_id, session_index) references public.sessions (run_id, session_index) on delete cascade
);

-- The Interlude's shuffled trial order, written when the Interlude starts.
create table public.interlude_plan (
    run_id        uuid not null,
    session_index integer not null,
    trial_order   jsonb not null,
    primary key (run_id, session_index),
    foreign key (run_id, session_index) references public.sessions (run_id, session_index) on delete cascade
);

create table public.interlude_trials (
    run_id              uuid not null,
    session_index       integer not null,
    seq                 integer not null check (seq >= 0),
    presented_order     integer not null,
    trial_index         integer not null,
    type                text,
    varied_feature      text,
    stage_x             double precision,
    stage_z             double precision,
    left_id             integer,
    left_shape          double precision,
    left_color          double precision,
    left_moisture       double precision,
    left_value          double precision,
    right_id            integer,
    right_shape         double precision,
    right_color         double precision,
    right_moisture      double precision,
    right_value         double precision,
    correct_side        text,
    choice              text,
    choice_correct      smallint,
    timed_out           smallint,
    response_time       double precision,
    first_harvest_time  double precision,
    first_harvest_side  text,
    left_fruits         integer,
    right_fruits        integer,
    bonus               double precision,
    locked_at           double precision,
    primary key (run_id, session_index, seq),
    foreign key (run_id, session_index) references public.sessions (run_id, session_index) on delete cascade
);

-- Registered at release time; run-start refuses a build that is not listed, and a session whose world or Interlude file
-- hash is not in `worlds` (the hash of either kind of file).
create table public.worlds (
    sha256        text primary key,
    name          text not null,
    registered_at timestamptz not null default now()
);

create table public.releases (
    build_commit  text primary key,
    n_sessions    integer,              -- sessions (practice, sessions, Interludes) a complete run of this build has
    note          text,
    registered_at timestamptz not null default now()
);

alter table public.runs             enable row level security;
alter table public.pid_registry     enable row level security;
alter table public.sessions         enable row level security;
alter table public.events           enable row level security;
alter table public.trajectory       enable row level security;
alter table public.interlude_plan   enable row level security;
alter table public.interlude_trials enable row level security;
alter table public.worlds           enable row level security;
alter table public.releases         enable row level security;

revoke all on public.runs, public.pid_registry, public.sessions, public.events, public.trajectory,
              public.interlude_plan, public.interlude_trials, public.worlds, public.releases
    from anon, authenticated;
