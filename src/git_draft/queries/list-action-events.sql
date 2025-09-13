select occurred_at, class, data
  from action_events as e
  join prompts as p on e.prompt_id = p.id
  where
      p.folio_id = :folio_id and
      p.seqno = coalesce(:seqno, (select max(seqno) from prompts where folio_id = :folio_id))
  order by occurred_at;
