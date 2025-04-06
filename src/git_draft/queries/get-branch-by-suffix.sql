select origin_branch, origin_sha
  from branches
  where suffix = :suffix;
