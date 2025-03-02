create table if not exists branches (
  suffix text primary key,
  created_at timestamp default current_timestamp,
  origin_branch text not null,
  origin_sha text not null,
  sync_sha text
) without rowid;

create table if not exists prompts (
  id integer primary key,
  created_at timestamp default current_timestamp,
  branch_suffix text not null,
  contents text not null,
  foreign key (branch_suffix) references branches(suffix)
);

create table if not exists commits (
  sha text primary key,
  created_at timestamp default current_timestamp,
  prompt_id integer not null,
  token_count int not null,
  walltime real not null,
  foreign key (prompt_id) references prompts(id)
) without rowid;
