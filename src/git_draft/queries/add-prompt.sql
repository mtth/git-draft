with
  seqnos as (
    select coalesce(count(*), 0) + 1 as seqno
      from prompts
      where folio_id = :folio_id)
insert into prompts (seqno, folio_id, template, contents)
  select seqno, :folio_id, :template, :contents
  from seqnos
  returning id, seqno
