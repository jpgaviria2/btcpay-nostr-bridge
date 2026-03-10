# BTCPay Nostr Bridge Refactor - March 8, 2026

## Changes Made

### Problem
The bridge was too rigid - it required campaign data (kind 9041 events) to exist on the relay before it would publish zap receipts. If campaigns weren't loaded or the relay was temporarily unreachable, payments would be processed by BTCPay but no Nostr receipts would be posted.

### Solution
Made campaign data **optional** - the bridge now always publishes zap receipts for payments, with or without campaign information.

## Technical Changes

### 1. Modified `nostr_client.py`
- `create_zap_receipt()`: Made `campaign_event_id` and `campaign_pubkey` optional
- Reordered parameters: `lightning_address` is now required and comes first
- Tag generation now conditional - campaign tags only added if data available
- **Required tags**: `lnurl` (lightning address) and `amount`
- **Optional tags**: `e` (campaign event), `p` (campaign creator)

### 2. Modified `service.py`
- Campaign lookup no longer fails the webhook
- Changed from "campaign not found → 404 error" to "campaign not found → publish basic receipt"
- Logs warning but continues processing
- Always publishes receipt with at minimum: amount + lightning address

## Benefits

1. **Resilience**: No more lost receipts due to campaign cache issues
2. **Simplicity**: UI handles aggregation, bridge just publishes data
3. **Flexibility**: Works with or without kind 9041 campaign events
4. **Recovery**: Even if relay is down during campaign refresh, payments still get receipts

## UI Impact

The Trails Coffee website (or any Nostr client) can now aggregate donations by:
1. Query relay for kind 9735 events
2. Filter by `lnurl` tag matching lightning address
3. Sum the `amount` tags
4. No dependency on campaign events

## Backwards Compatibility

✅ **Fully backwards compatible**
- Events with campaign data work exactly as before
- Events without campaign data now also work (new feature)
- Existing UIs that look for campaign tags will still find them when available

## Testing

Tested both scenarios:
- ✅ Payment WITH campaign data (scouts/torca/pac@anmore.cash)
- ✅ Payment WITHOUT campaign data (unknown addresses)

Both post valid kind 9735 zap receipts to relay.

## Production Deployment

Deployed: March 8, 2026 15:45 PST
Service: btcpay-nostr-bridge (systemd)
Status: ✅ Running

Backups created:
- service.py.backup-refactor-20260308-1545
- nostr_client.py.backup-refactor-20260308-1545
