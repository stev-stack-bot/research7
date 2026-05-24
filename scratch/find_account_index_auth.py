import os
import sys
import time
import ctypes
import platform
import asyncio
import aiohttp

ENV = {}
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and "=" in line:
                k, v = line.split("=", 1)
                ENV[k.strip()] = v.strip()

API_KEY_PRIV = ENV.get("lighter_api_private", "656709f6a5aae04da05425bd4c1a2239f92f1acc897586b1cd0afcb115abb89e9836531a2a21ea58")
API_KEY_INDEX = int(ENV.get("lighter_api_index", "67"))
BASE_URL = "https://mainnet.zklighter.elliot.ai"

# Define CTypes structures
class StrOrErr(ctypes.Structure):
    _fields_ = [('str', ctypes.c_void_p), ('err', ctypes.c_void_p)]

# Load shared signer library
def load_signer_library():
    import lighter
    pkg_dir = os.path.dirname(lighter.__file__)
    path_to_signers = os.path.join(pkg_dir, "signers")
    lib_path = os.path.join(path_to_signers, "lighter-signer-linux-amd64.so")
    signer = ctypes.CDLL(lib_path)
    
    signer.CreateClient.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_longlong]
    signer.CreateClient.restype = ctypes.c_void_p

    signer.CreateAuthToken.argtypes = [ctypes.c_longlong, ctypes.c_int, ctypes.c_longlong]
    signer.CreateAuthToken.restype = StrOrErr

    signer.Free.argtypes = [ctypes.c_void_p]
    signer.Free.restype = None
    
    return signer

SIGNER = load_signer_library()

def decode_and_free(ptr):
    if not ptr:
        return None
    try:
        c_str = ctypes.cast(ptr, ctypes.c_char_p).value
        if c_str is not None:
            return c_str.decode('utf-8')
        return None
    finally:
        SIGNER.Free(ptr)

def generate_auth_token_offline(account_index):
    # Register client offline
    err_ptr = SIGNER.CreateClient(
        BASE_URL.encode('utf-8'),
        API_KEY_PRIV.encode('utf-8'),
        304,
        API_KEY_INDEX,
        account_index
    )
    err = decode_and_free(err_ptr)
    if err:
        return None

    # Generate Auth Token
    timestamp = int(time.time())
    deadline = 3600
    result = SIGNER.CreateAuthToken(timestamp + deadline, API_KEY_INDEX, account_index)
    auth = decode_and_free(result.str)
    return auth

async def check_index(session, idx):
    auth_token = generate_auth_token_offline(idx)
    if not auth_token:
        return None
        
    url = f"{BASE_URL}/api/v1/export?account_index={idx}&market_id=0&type=trade"
    headers = {"Authorization": auth_token}
    try:
        async with session.get(url, headers=headers, timeout=5) as response:
            text = await response.text()
            # If the index is valid for this account, it should not return 401 with invalid auth.
            if response.status == 200:
                print(f"\nFOUND VALID ACCOUNT INDEX: {idx}")
                print(f"Response: {text}")
                sys.exit(0)
            elif response.status == 401:
                # "invalid auth: couldnt find account" or similar means wrong index
                pass
            else:
                # Any other status code indicates success or a different issue
                print(f"\nPossible index: {idx} (Status {response.status}): {text}")
    except Exception as e:
        pass
    return None

async def main():
    print("Starting authenticated account index discovery...")
    
    # Scan candidate ranges
    ranges = [
        (0, 10000),       # Retail / standard low indexes
        (700000, 750000), # Observed range in trade data
        (200000, 250000), # Observed range in trade data
        (10000, 200000),
        (250000, 700000),
        (750000, 1000000)
    ]
    
    connector = aiohttp.TCPConnector(limit=100)
    async with aiohttp.ClientSession(connector=connector) as session:
        for start, end in ranges:
            print(f"Scanning range {start} to {end}...")
            chunk_size = 200
            for chunk_start in range(start, end, chunk_size):
                tasks = [check_index(session, idx) for idx in range(chunk_start, min(chunk_start + chunk_size, end))]
                await asyncio.gather(*tasks)
                await asyncio.sleep(0.05)
    print("Discovery completed. No active index found in ranges.")

if __name__ == "__main__":
    asyncio.run(main())
