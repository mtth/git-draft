select repo_uuid, origin_branch, origin_sha
  from folios
  where id = :id;
