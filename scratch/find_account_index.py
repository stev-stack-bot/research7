import asyncio
import aiohttp
import sys

TARGET_PUBKEY = "fca9d0e13c65e56d009cf6035b43586cd579646ba59bc3e8542f0a52ea61e860a4a3f7c0d0290625"
BASE_URL = "https://mainnet.zklighter.elliot.ai"

async def check_index(session, idx):
    url = f"{BASE_URL}/api/v1/apikeys?account_index={idx}&api_key_index=255"
    try:
        async with session.get(url, timeout=3) as response:
            if response.status == 200:
                data = await response.json()
                if "api_keys" in data:
                    for key_info in data["api_keys"]:
                        pub_key = key_info.get("public_key")
                        if pub_key == TARGET_PUBKEY:
                            print(f"\nFOUND! Account Index: {idx}")
                            print(f"Key info: {key_info}")
                            sys.exit(0)
    except Exception as e:
        pass

async def main():
    print(f"Searching for account index containing public key: {TARGET_PUBKEY}")
    
    # Configure TCPConnector to limit connection pooling and increase limits
    connector = aiohttp.TCPConnector(limit=500)
    async with aiohttp.ClientSession(connector=connector) as session:
        chunk_size = 500
        for start in range(10000, 100000, chunk_size):
            print(f"Scanning indices {start} to {start + chunk_size}...")
            tasks = [check_index(session, idx) for idx in range(start, start + chunk_size)]
            await asyncio.gather(*tasks)
            await asyncio.sleep(0.05)
    print("Done scanning. Not found in 10000-100000.")

if __name__ == "__main__":
    asyncio.run(main())
