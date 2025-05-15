select p.contents, a.question
  from prompts as p
  join folios as f on p.folio_id = f.id
  left join actions as a on p.id = a.prompt_id
  where f.id = :folio_id
  order by p.id desc
  limit 1;
