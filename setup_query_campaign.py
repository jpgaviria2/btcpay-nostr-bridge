#!/usr/bin/env python3
"""
Query relay.anmore.me for kind 9041 fundraising campaigns
Run this to find your campaign event ID and creator pubkey
"""
import json
import asyncio
import websockets
import sys

RELAY_URL = "wss://relay.anmore.me"

async def query_campaigns():
    """Query the relay for kind 9041 fundraising campaigns"""
    
    print(f"Connecting to {RELAY_URL}...")
    print("=" * 80)
    
    try:
        async with websockets.connect(RELAY_URL) as websocket:
            # Subscribe to kind 9041 events
            subscription_id = "query_campaigns"
            request = json.dumps([
                "REQ",
                subscription_id,
                {
                    "kinds": [9041],
                    "limit": 50
                }
            ])
            
            await websocket.send(request)
            print("Querying for kind 9041 (fundraising) events...")
            print("=" * 80)
            
            campaigns_found = []
            timeout = 5  # seconds
            
            try:
                async with asyncio.timeout(timeout):
                    while True:
                        response = await websocket.recv()
                        data = json.loads(response)
                        
                        if data[0] == "EVENT":
                            event = data[2]
                            campaigns_found.append(event)
                            
                            # Extract information
                            event_id = event.get('id', 'N/A')
                            pubkey = event.get('pubkey', 'N/A')
                            content = event.get('content', 'Untitled')
                            created_at = event.get('created_at', 0)
                            
                            # Extract tags
                            tags = event.get('tags', [])
                            amount = None
                            summary = None
                            lnaddress = None
                            
                            for tag in tags:
                                if len(tag) < 2:
                                    continue
                                if tag[0] == 'amount':
                                    amount = tag[1]
                                elif tag[0] == 'summary':
                                    summary = tag[1]
                                elif tag[0] in ['zap', 'lnaddress']:
                                    lnaddress = tag[1]
                            
                            print(f"\nCampaign #{len(campaigns_found)}:")
                            print(f"  Title: {content}")
                            print(f"  Event ID: {event_id}")
                            print(f"  Creator: {pubkey}")
                            if summary:
                                print(f"  Summary: {summary}")
                            if amount:
                                print(f"  Goal: {amount} sats")
                            if lnaddress:
                                print(f"  Lightning: {lnaddress}")
                            print(f"  Created: {created_at}")
                            print("-" * 80)
                        
                        elif data[0] == "EOSE":
                            break
            
            except asyncio.TimeoutError:
                pass
            
            # Close subscription
            close_msg = json.dumps(["CLOSE", subscription_id])
            await websocket.send(close_msg)
            
            print(f"\nFound {len(campaigns_found)} campaign(s)")
            
            if campaigns_found:
                print("\n" + "=" * 80)
                print("CONFIGURATION VALUES FOR .env FILE:")
                print("=" * 80)
                
                for i, campaign in enumerate(campaigns_found, 1):
                    if len(campaigns_found) > 1:
                        # Get title from content
                        title = campaign.get('content', 'Untitled')[:40]
                        print(f"\n# Campaign {i}: {title}")
                    
                    print(f"CAMPAIGN_EVENT_ID={campaign['id']}")
                    print(f"CAMPAIGN_CREATOR_PUBKEY={campaign['pubkey']}")
                    
                    # Show lightning address if available
                    for tag in campaign.get('tags', []):
                        if len(tag) >= 2 and tag[0] in ['zap', 'lnaddress']:
                            print(f"# Lightning Address: {tag[1]}")
                            break
                    
                    if len(campaigns_found) > 1:
                        print()
                
                print("\nCopy the values above to your .env file")
                return 0
            else:
                print("\n❌ No fundraising campaigns found!")
                print("\nYou need to create a kind 9041 event first.")
                print("The fundraising campaign should:")
                print("  - Be kind 9041 (Zap Goal)")
                print("  - Have a 'zap' or 'lnaddress' tag with Lightning address")
                print("  - Be published to relay.anmore.me")
                return 1
                
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(query_campaigns()))

