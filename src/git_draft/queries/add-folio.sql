insert into folios (repo_uuid, origin_branch, origin_sha)
  values (:repo_uuid, :origin_branch, :origin_sha)
  returning id;
