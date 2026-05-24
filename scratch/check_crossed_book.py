import json

def check_book():
    current_bids = {}
    current_asks = {}
    
    with open("data/raw_lighter_book_0.jsonl", "r") as f:
        for line_num, line in enumerate(f, 1):
            msg = json.loads(line)
            ob_data = msg.get("order_book", {})
            if not ob_data:
                continue
                
            # If snapshot is received, clear local state to prevent stale levels
            if len(ob_data.get("bids", [])) > 100 or len(ob_data.get("asks", [])) > 100:
                current_bids.clear()
                current_asks.clear()
                
            # update bids
            for b in ob_data.get("bids", []):
                price = float(b["price"])
                size = float(b["size"])
                if size == 0.0:
                    current_bids.pop(price, None)
                else:
                    current_bids[price] = size
                    
            # update asks
            for a in ob_data.get("asks", []):
                price = float(a["price"])
                size = float(a["size"])
                if size == 0.0:
                    current_asks.pop(price, None)
                else:
                    current_asks[price] = size

                    
            if current_bids and current_asks:
                best_bid = max(current_bids.keys())
                best_ask = min(current_asks.keys())
                if best_bid >= best_ask:
                    print(f"Book crossed at line {line_num}!")
                    print(f"Best Bid: {best_bid} | Best Ask: {best_ask} | Spread: {best_ask - best_bid}")
                    print("Bids near best bid:", sorted(current_bids.keys(), reverse=True)[:5])
                    print("Asks near best ask:", sorted(current_asks.keys())[:5])
                    print("Message update bids:", ob_data.get("bids", []))
                    print("Message update asks:", ob_data.get("asks", []))
                    break

if __name__ == "__main__":
    check_book()
