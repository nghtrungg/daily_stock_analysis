-- Preserve source-name scoped intelligence deduplication when source_id is NULL.
create unique index if not exists uix_intel_item_null_source_scope_url
on dsa.intelligence_items (
  coalesce(source_name, ''),
  url,
  source_type,
  scope_type,
  scope_value,
  market
)
where source_id is null;
