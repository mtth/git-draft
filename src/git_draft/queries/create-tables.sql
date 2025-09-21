create table if not exists folios (
  id integer primary key,
  repo_uuid text not null,
  created_at timestamp default current_timestamp,
  origin_branch text not null
);

create index if not exists folios_by_repo on folios (repo_uuid);

create table if not exists prompts (
  id integer primary key,
  folio_id integer not null,
  seqno integer not null,
  created_at timestamp default current_timestamp,
  template text,
  contents text not null,
  foreign key (folio_id) references folios(id)
);

create unique index if not exists prompts_by_folio_seqno on prompts (folio_id, seqno);

create table if not exists action_summaries (
  prompt_id integer primary key,
  created_at timestamp default current_timestamp,
  bot_class text not null,
  walltime_seconds real not null,
  turn_count int,
  token_count int,
  pending_question text,
  foreign key (prompt_id) references prompts (id) on delete cascade
) without rowid;

create table if not exists action_events (
  id integer primary key,
  prompt_id integer not null,
  occurred_at timestamp default current_timestamp,
  class text not null,
  data text not null,
  foreign key (prompt_id) references action_summaries (prompt_id) on delete cascade
);
