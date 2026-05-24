import json
import os
import sys

def audit_files():
    book_file_path = "data/raw_lighter_book_0.jsonl"
    trades_file_path = "data/raw_lighter_trades_0.jsonl"
    
    if not os.path.exists(book_file_path) or not os.path.exists(trades_file_path):
        print("Data files not found. Run recorder first.")
        return
        
    print("=== Auditing Lighter Order Book Feed ===")
    book_count = 0
    nonces = []
    begin_nonces = []
    offsets = []
    book_timestamps = []
    book_last_updated = []
    null_fields_book = 0
    empty_books = 0
    
    with open(book_file_path, "r") as f:
        for line in f:
            book_count += 1
            msg = json.loads(line)
            
            # Check structure
            if "type" in msg and msg["type"] == "subscribed/candle":
                continue # ignore if any other type
                
            order_book_obj = msg.get("order_book", {})
            if not order_book_obj:
                null_fields_book += 1
                continue
                
            nonce = order_book_obj.get("nonce")
            begin_nonce = order_book_obj.get("begin_nonce")
            offset = order_book_obj.get("offset")
            last_updated = order_book_obj.get("last_updated_at")
            timestamp = msg.get("timestamp")
            
            if nonce is not None: nonces.append(nonce)
            if begin_nonce is not None: begin_nonces.append(begin_nonce)
            if offset is not None: offsets.append(offset)
            if last_updated is not None: book_last_updated.append(last_updated)
            if timestamp is not None: book_timestamps.append(timestamp)
            
            asks = order_book_obj.get("asks", [])
            bids = order_book_obj.get("bids", [])
            if not asks and not bids:
                empty_books += 1
                
    print(f"Total book updates read: {book_count}")
    print(f"Updates with null order_book field: {null_fields_book}")
    print(f"Empty book updates (no asks/bids changes): {empty_books}")
    if nonces:
        print(f"Nonce range: {min(nonces)} to {max(nonces)}")
        # Check continuity: begin_nonce should match previous nonce
        discontinuities = 0
        for i in range(1, len(nonces)):
            if begin_nonces[i] != nonces[i-1]:
                discontinuities += 1
        print(f"Continuity checks: Found {discontinuities} gaps/reconnections in nonce sequence.")
    if book_timestamps:
        print(f"Timestamp range (ms): {min(book_timestamps)} to {max(book_timestamps)}")
        print(f"Last updated at (us): {min(book_last_updated)} to {max(book_last_updated)}")
        
    print("\n=== Auditing Lighter Trades Feed ===")
    trades_count = 0
    trade_ids = []
    trade_timestamps = []
    trade_transaction_times = []
    total_trades_received = 0
    liquidation_trades_count = 0
    null_fields_trade = 0
    
    with open(trades_file_path, "r") as f:
        for line in f:
            trades_count += 1
            msg = json.loads(line)
            
            trades_list = msg.get("trades")
            liqs_list = msg.get("liquidation_trades")
            
            if trades_list is None:
                null_fields_trade += 1
                continue
                
            total_trades_received += len(trades_list)
            if liqs_list:
                liquidation_trades_count += len(liqs_list)
                
            for t in trades_list:
                t_id = t.get("trade_id")
                ts = t.get("timestamp")
                tx_t = t.get("transaction_time")
                
                if t_id is not None: trade_ids.append(t_id)
                if ts is not None: trade_timestamps.append(ts)
                if tx_t is not None: trade_transaction_times.append(tx_t)
                
    print(f"Total trade stream messages read: {trades_count}")
    print(f"Total individual trades received: {total_trades_received}")
    print(f"Total liquidation trades received: {liquidation_trades_count}")
    if trade_ids:
        print(f"Trade ID range: {min(trade_ids)} to {max(trade_ids)}")
        print(f"Trade timestamps (ms): {min(trade_timestamps)} to {max(trade_timestamps)}")
        print(f"Trade transaction times (us): {min(trade_transaction_times)} to {max(trade_transaction_times)}")
        
        # Check for duplicate trade IDs
        unique_tids = len(set(trade_ids))
        print(f"Duplicate trade IDs: {len(trade_ids) - unique_tids}")

if __name__ == "__main__":
    audit_files()
