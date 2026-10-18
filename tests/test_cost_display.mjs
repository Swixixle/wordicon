import assert from 'node:assert/strict';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('../webapp/work/cost-display.js',import.meta.url),'utf8');
const {estimatedDollars,costText,cacheReadText}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const calls={estimated_cost_usd:0.129876543,known_estimated_subtotal_usd:0.129876543,accounting_status:'estimated',
  entries:[{basis:'provider_usage_rate_card_estimate',usage:[{category:'cache_read_input_tokens',count:0}]}]};
const original=JSON.stringify(calls);
assert.match(costText(calls,'Four calls'),/about \$0.13 estimated.*provider-billed amount unconfirmed/);
assert.match(costText({...calls,estimated_cost_usd:0.192345678},'Including earlier calls'),/about \$0.19 estimated/);
assert.equal(JSON.stringify(calls),original,'presentation never rounds ledger values');
assert.match(costText({...calls,estimated_cost_usd:null,accounting_status:'unknown'},'Cost'),/total unknown · known subtotal about \$0.13 estimated/);
assert.match(costText({estimated_cost_usd:null,known_estimated_subtotal_usd:null},'Cost'),/total unknown.*estimate unavailable/);
assert.equal(estimatedDollars(.000031),'less than $0.01 estimated','small positive charges do not round to free');
assert.match(cacheReadText(calls),/cache-read tokens: 0 recorded/);
assert.match(cacheReadText(calls),/no provider cache savings are inferred/);
assert.match(cacheReadText({entries:[{usage:[{category:'cache_read_input_tokens',count:null}]}]}),/some usage unavailable/);
assert.match(cacheReadText({}),/unavailable/);
assert.equal(JSON.stringify(calls),original);
console.log('Cost display: 11 checks passed');
