import asyncio
import lighter
import time

URL = "https://mainnet.zklighter.elliot.ai"
API_KEY_INDEX = 67
API_KEY_PRIVATE = "656709f6a5aae04da05425bd4c1a2239f92f1acc897586b1cd0afcb115abb89e9836531a2a21ea58"

async def test():
    t0 = time.time()
    try:
        client = lighter.SignerClient(
            url=URL,
            account_index=0,
            api_private_keys={API_KEY_INDEX: API_KEY_PRIVATE}
        )
        print("Initialized client")
        err = client.check_client()
        print(f"check_client result: {err}")
    except Exception as e:
        print(f"Error: {e}")
    print(f"Time taken: {time.time() - t0:.4f}s")

if __name__ == "__main__":
    asyncio.run(test())
