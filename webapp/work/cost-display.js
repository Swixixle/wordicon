// Presentation only. Accounting keeps its full precision and provider receipts.
// A rounded estimate is neither an allowance nor a final invoice.
export function estimatedDollars(value) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return 'estimate unavailable';
  if (value > 0 && value < 0.005) return 'less than $0.01 estimated';
  return 'about $' + value.toFixed(2) + ' estimated';
}

export function costText(value, label) {
  if (!value) return label + ': accounting unavailable';
  const unknown = value.estimated_cost_usd == null || ['unknown','partial'].includes(value.accounting_status) ||
    (value.unknown_components || []).length > 0 || (value.unaccounted_operation_ids || []).length > 0;
  const amount = estimatedDollars(unknown ? value.known_estimated_subtotal_usd : value.estimated_cost_usd);
  return label + ': ' + (unknown ? 'total unknown · known subtotal ' : '') + amount +
    (unknown ? ' · unresolved usage remains' : '') + ' · provider-billed amount unconfirmed';
}

export function cacheReadText(accounting) {
  const entries = accounting?.entries;
  if (!Array.isArray(entries)) return 'Provider cache-read tokens: unavailable. Local source reuse is separate.';
  const paid = entries.filter(e => e.basis !== 'upstream_zero_model_collection_contract');
  let total = 0, unknown = false;
  for (const entry of paid) {
    if (entry.usage_complete === false) unknown = true;
    const row = Array.isArray(entry.usage) && entry.usage.find(u => u.category === 'cache_read_input_tokens');
    if (!row || typeof row.count !== 'number' || !Number.isFinite(row.count) || row.count < 0) unknown = true;
    else total += row.count;
  }
  if (!paid.length) return 'Provider cache-read tokens: unavailable. Local source reuse is separate.';
  return 'Provider cache-read tokens: ' + total + (unknown ? ' known; some usage unavailable' : ' recorded') +
    '. Local source reuse is separate; no provider cache savings are inferred.';
}
