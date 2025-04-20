insert into folios (repo_uuid, origin_branch)
  values (:repo_uuid, :origin_branch)
  returning id;
