select
    datetime(min(p.created_at), 'localtime') as created,
    coalesce(min(template), '-') as template,
    coalesce(min(a.bot_name), '-') as bot,
    coalesce(round(sum(a.walltime), 1), 0) as walltime,
    count(o.id) as ops
  from prompts as p
  join branches as b on p.branch_suffix = b.suffix
  left join actions as a on p.id = a.prompt_id
  left join operations as o on a.commit_sha = o.action_commit_sha
  where b.repo_path = :repo_path and b.suffix = :branch_suffix
  group by p.id
  order by created desc;
