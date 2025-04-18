select p.contents
  from prompts as p
  join folios as f on p.folio_id = f.id
  where f.id = :folio_id
  order by p.id desc
  limit 1;
