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

create table if not exists actions (
  prompt_id integer primary key,
  created_at timestamp default current_timestamp,
  bot_class text not null,
  walltime_seconds real not null,
  request_count int,
  token_count int,
  question text,
  foreign key (prompt_id) references prompts (id) on delete cascade
) without rowid;

create table if not exists operations (
  id integer primary key,
  prompt_id integer not null,
  tool text not null,
  reason text,
  details text not null,
  started_at timestamp not null,
  foreign key (prompt_id) references actions (prompt_id) on delete cascade
);
