import asyncio
import json
import os
import sys
import time
import websockets

async def record_feed(coin, duration_sec, output_dir):
    uri = "wss://api.hyperliquid.xyz/ws"
    book_file_path = os.path.join(output_dir, f"raw_book_{coin}.jsonl")
    trades_file_path = os.path.join(output_dir, f"raw_trades_{coin}.jsonl")
    
    # Open files for writing JSON-L
    book_file = open(book_file_path, "a")
    trades_file = open(trades_file_path, "a")
    
    print(f"Connecting to Hyperliquid WebSocket for {coin}...")
    print(f"Recording to {book_file_path} and {trades_file_path}...")
    
    start_time = time.time()
    
    try:
        async with websockets.connect(uri) as websocket:
            # Subscribe to L2 Book
            subscribe_book = {
                "method": "subscribe",
                "subscription": {"type": "l2Book", "coin": coin}
            }
            await websocket.send(json.dumps(subscribe_book))
            
            # Subscribe to Trades
            subscribe_trades = {
                "method": "subscribe",
                "subscription": {"type": "trades", "coin": coin}
            }
            await websocket.send(json.dumps(subscribe_trades))
            
            print("Subscriptions sent. Recording started...")
            
            while time.time() - start_time < duration_sec:
                try:
                    # Wait for message with a timeout to check duration limit
                    message_str = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    msg = json.loads(message_str)
                    
                    channel = msg.get("channel")
                    data = msg.get("data")
                    
                    if not data:
                        continue
                    
                    # Log message based on channel type
                    if channel == "l2Book":
                        # Record format: timestamp, coin, levels [bids, asks]
                        record = {
                            "time": data.get("time"),
                            "coin": data.get("coin"),
                            "levels": data.get("levels")
                        }
                        book_file.write(json.dumps(record) + "\n")
                        book_file.flush()
                    elif channel == "trades":
                        # data is a list of WsTrade
                        for trade in data:
                            record = {
                                "time": trade.get("time"),
                                "coin": trade.get("coin"),
                                "px": trade.get("px"),
                                "sz": trade.get("sz"),
                                "side": trade.get("side"),
                                "hash": trade.get("hash"),
                                "tid": trade.get("tid")
                            }
                            trades_file.write(json.dumps(record) + "\n")
                            trades_file.flush()
                            
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
    coin_symbol = "BTC" if len(sys.argv) < 2 else sys.argv[1]
    duration = 60 if len(sys.argv) < 3 else int(sys.argv[2])
    out_dir = "data" if len(sys.argv) < 4 else sys.argv[3]
    
    os.makedirs(out_dir, exist_ok=True)
    
    asyncio.run(record_feed(coin_symbol, duration, out_dir))
