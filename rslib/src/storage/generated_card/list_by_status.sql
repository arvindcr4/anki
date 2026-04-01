SELECT id,
  front,
  back,
  source_url,
  source_type,
  created_at,
  sync_status,
  tags,
  is_cloze
FROM generated_cards
WHERE sync_status = ?
ORDER BY created_at DESC