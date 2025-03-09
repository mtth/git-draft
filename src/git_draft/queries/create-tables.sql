create table if not exists branches (
  suffix text primary key,
  repo_path text not null,
  created_at timestamp default current_timestamp,
  origin_branch text not null,
  origin_sha text not null,
  sync_sha text
) without rowid;

create table if not exists prompts (
  id integer primary key,
  created_at timestamp default current_timestamp,
  branch_suffix text not null,
  template text,
  contents text not null,
  foreign key (branch_suffix) references branches(suffix)
);

create table if not exists actions (
  commit_sha text primary key,
  created_at timestamp default current_timestamp,
  prompt_id integer not null,
  bot_name text,
  bot_class text not null,
  walltime real not null,
  request_count int,
  token_count int,
  foreign key (prompt_id) references prompts(id) on delete cascade
) without rowid;

create table if not exists operations (
  id integer primary key,
  action_commit_sha text not null,
  tool text not null,
  reason text,
  details text not null,
  started_at timestamp not null,
  foreign key (action_commit_sha) references actions(commit_sha) on delete cascade
);
