import asyncio
import json
import os
import sys
import time
import websockets

async def record_feed(market_id, duration_sec, output_dir):
    uri = "wss://mainnet.zklighter.elliot.ai/stream?readonly=true"
    book_file_path = os.path.join(output_dir, f"raw_lighter_book_{market_id}.jsonl")
    trades_file_path = os.path.join(output_dir, f"raw_lighter_trades_{market_id}.jsonl")
    
    # Open files for writing JSON-L
    book_file = open(book_file_path, "a")
    trades_file = open(trades_file_path, "a")
    
    print(f"Connecting to Lighter WebSocket for market {market_id}...")
    print(f"Recording to {book_file_path} and {trades_file_path}...")
    
    start_time = time.time()
    
    try:
        async with websockets.connect(uri) as websocket:
            # Subscribe to Order Book
            subscribe_book = {
                "type": "subscribe",
                "channel": f"order_book/{market_id}"
            }
            await websocket.send(json.dumps(subscribe_book))
            
            # Subscribe to Trades
            subscribe_trades = {
                "type": "subscribe",
                "channel": f"trade/{market_id}"
            }
            await websocket.send(json.dumps(subscribe_trades))
            
            print("Subscriptions sent. Recording started...")
            
            # Record loop
            while time.time() - start_time < duration_sec:
                try:
                    # Wait for message with a timeout to check duration limit
                    message_str = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    msg = json.loads(message_str)
                    
                    msg_type = msg.get("type")
                    channel = msg.get("channel")
                    
                    if not msg_type or not channel:
                        continue
                    
                    # Log message based on channel type
                    if msg_type == "update/order_book":
                        book_file.write(json.dumps(msg) + "\n")
                        book_file.flush()
                    elif msg_type == "update/trade":
                        trades_file.write(json.dumps(msg) + "\n")
                        trades_file.flush()
                    elif msg_type.startswith("subscribed/"):
                        # Record subscription confirmation snapshots if they contain data
                        if "order_book" in msg_type or "order_book" in channel:
                            book_file.write(json.dumps(msg) + "\n")
                            book_file.flush()
                            print(f"Snapshot received for {channel}")
                            
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    print(f"Error receiving message: {e}", file=sys.stderr)
                    break
    finally:
        book_file.close()
        trades_file.close()
        print(f"Recording completed. Total elapsed time: {time.time() - start_time:.2f} seconds.")

if __name__ == "__main__":
    market = "0" if len(sys.argv) < 2 else sys.argv[1]
    duration = 60 if len(sys.argv) < 3 else int(sys.argv[2])
    out_dir = "data" if len(sys.argv) < 4 else sys.argv[3]
    
    os.makedirs(out_dir, exist_ok=True)
    
    asyncio.run(record_feed(market, duration, out_dir))
