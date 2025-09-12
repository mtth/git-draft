select p.contents, s.pending_question
  from prompts as p
  join folios as f on p.folio_id = f.id
  left join action_summaries as s on p.id = s.prompt_id
  where f.id = :folio_id
  order by p.id desc
  limit 1;
