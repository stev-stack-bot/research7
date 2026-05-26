import os
import glob
import io
import json
import zstandard as zstd

def test():
    data_dir = "/kaggle/research7/data"
    trade_files = sorted(glob.glob(os.path.join(data_dir, "raw_lighter_trades_0_*.jsonl.zst")))
    print(f"Found {len(trade_files)} trade files for market 0.")
    if not trade_files:
        return
    
    # Read first 5 lines of the first file
    dctx = zstd.ZstdDecompressor()
    with open(trade_files[0], 'rb') as fh:
        with dctx.stream_reader(fh) as reader:
            text_stream = io.TextIOWrapper(reader, encoding='utf-8')
            for i, line in enumerate(text_stream):
                if i >= 5:
                    break
                msg = json.loads(line)
                print(f"Line {i}: {list(msg.keys())}")

if __name__ == "__main__":
    test()
