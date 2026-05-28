import os
import sys
import json

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.run_lighter_pipeline_v5 import run_market_backtest_v5

def main():
    if len(sys.argv) < 2:
        print("Usage: python print_v5_scorecard.py <symbol>")
        return
    sym = sys.argv[1].upper()
    
    # Run the backtester
    res = run_market_backtest_v5(sym)
    if res:
        out_path = f"data/v5_scorecard_{sym}.json"
        with open(out_path, "w") as f:
            # We convert DataFrames to dict or drop them to be JSON serializable
            output_data = {
                "symbol": res["symbol"],
                "bench_ret": res["bench_ret"],
                "std_baseline": res["std_baseline"]["metrics"],
                "std_meta": res["std_meta"]["metrics"],
                "prem_baseline": res["prem_baseline"]["metrics"],
                "prem_meta": res["prem_meta"]["metrics"]
            }
            json.dump(output_data, f, indent=4)
        print(f"Successfully saved scorecard for {sym} to {out_path}")

if __name__ == "__main__":
    main()
