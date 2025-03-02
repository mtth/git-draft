select origin_branch, origin_sha, sync_sha
  from branches
  where suffix = :suffix;
