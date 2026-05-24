import os
import sys
import time
import ctypes
import platform
import asyncio
import aiohttp
import requests

# Load .env variables
def load_env():
    env_vars = {}
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()
    return env_vars

ENV = load_env()
API_KEY_PUB = ENV.get("lighter_api_pub", "fca9d0e13c65e56d009cf6035b43586cd579646ba59bc3e8542f0a52ea61e860a4a3f7c0d0290625")
API_KEY_PRIV = ENV.get("lighter_api_private", "656709f6a5aae04da05425bd4c1a2239f92f1acc897586b1cd0afcb115abb89e9836531a2a21ea58")
API_KEY_INDEX = int(ENV.get("lighter_api_index", "67"))
BASE_URL = "https://mainnet.zklighter.elliot.ai"

# Define CTypes structures
class StrOrErr(ctypes.Structure):
    _fields_ = [('str', ctypes.c_void_p), ('err', ctypes.c_void_p)]

# Load shared signer library
def load_signer_library():
    try:
        import lighter
    except ImportError:
        print("Error: 'lighter' package not installed. Run 'pip install lighter-sdk'")
        sys.exit(1)
        
    is_linux = platform.system() == "Linux"
    is_mac = platform.system() == "Darwin"
    is_windows = platform.system() == "Windows"
    is_x64 = platform.machine().lower() in ("amd64", "x86_64")
    is_arm = platform.machine().lower() in ("arm64", "aarch64")

    pkg_dir = os.path.dirname(lighter.__file__)
    path_to_signers = os.path.join(pkg_dir, "signers")

    if is_arm and is_mac:
        lib_name = "lighter-signer-darwin-arm64.dylib"
    elif is_linux and is_x64:
        lib_name = "lighter-signer-linux-amd64.so"
    elif is_linux and is_arm:
        lib_name = "lighter-signer-linux-arm64.so"
    elif is_windows and is_x64:
        lib_name = "lighter-signer-windows-amd64.dll"
    else:
        raise Exception(f"Unsupported platform/architecture: {platform.system()}/{platform.machine()}")

    lib_path = os.path.join(path_to_signers, lib_name)
    if not os.path.exists(lib_path):
        raise FileNotFoundError(f"Signer shared library not found at: {lib_path}")
        
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
        304, # Mainnet chain_id
        API_KEY_INDEX,
        account_index
    )
    err = decode_and_free(err_ptr)
    if err:
        raise Exception(f"Failed to create offline client: {err}")

    # Generate Auth Token
    timestamp = int(time.time())
    deadline = 28800 # 8 hours (maximum allowed expiry)
    result = SIGNER.CreateAuthToken(timestamp + deadline, API_KEY_INDEX, account_index)
    auth = decode_and_free(result.str)
    error = decode_and_free(result.err)
    if error:
        raise Exception(f"Failed to sign auth token: {error}")
    return auth

async def check_index(session, idx):
    url = f"{BASE_URL}/api/v1/apikeys?account_index={idx}&api_key_index=255"
    try:
        async with session.get(url, timeout=4) as response:
            if response.status == 200:
                data = await response.json()
                if "api_keys" in data:
                    for key_info in data["api_keys"]:
                        if key_info.get("public_key") == API_KEY_PUB:
                            return idx
            elif response.status == 403:
                # CloudFront blocking
                text = await response.text()
                if "CloudFront" in text or "Request blocked" in text:
                    print("\n[!] CloudFront block detected. Run this script locally where your IP is not blocked.")
                    sys.exit(1)
    except Exception:
        pass
    return None

async def discover_account_index():
    print(f"Scanning Lighter account indices for public key: {API_KEY_PUB}...")
    
    # We scan around active ranges found in trade data (e.g. 100k to 900k)
    # Plus standard ranges (0 to 100k)
    ranges_to_scan = [
        (0, 50000),
        (50000, 100000),
        (700000, 750000),
        (750000, 800000),
        (100000, 700000),
        (800000, 1000000)
    ]
    
    connector = aiohttp.TCPConnector(limit=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        for start, end in ranges_to_scan:
            print(f"Scanning range {start} to {end}...")
            chunk_size = 500
            for chunk_start in range(start, end, chunk_size):
                tasks = [check_index(session, idx) for idx in range(chunk_start, min(chunk_start + chunk_size, end))]
                results = await asyncio.gather(*tasks)
                for r in results:
                    if r is not None:
                        return r
                await asyncio.sleep(0.02)
    return None

def trigger_export(account_index, auth_token, export_type="trade", market_id=0):
    url = f"{BASE_URL}/api/v1/export"
    params = {
        "account_index": account_index,
        "market_id": market_id,
        "type": export_type
    }
    headers = {
        "Authorization": auth_token
    }
    print(f"Requesting export of type '{export_type}' for market {market_id}...")
    response = requests.get(url, params=params, headers=headers)
    if response.status_code != 200:
        print(f"Export request failed (HTTP {response.status_code}): {response.text}")
        if response.status_code == 403:
            print("[!] Request blocked by CloudFront WAF. Run this script from a residential/authorized IP.")
        sys.exit(1)
        
    data = response.json()
    if data.get("code") != 200:
        raise Exception(f"API Error: {data.get('message')}")
        
    return data.get("data_url")

def download_file(url, output_path):
    print(f"Downloading export file from: {url}")
    response = requests.get(url, stream=True)
    if response.status_code != 200:
         raise Exception(f"Download failed (HTTP {response.status_code})")
    
    with open(output_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    print(f"Successfully downloaded to: {output_path}")

async def run_pipeline():
    # 1. Discover account index
    account_index = None
    
    # Check if specified in arguments
    if len(sys.argv) > 1:
        try:
            account_index = int(sys.argv[1])
            print(f"Using provided account index: {account_index}")
        except ValueError:
            pass
            
    if account_index is None:
        account_index = await discover_account_index()
        
    if account_index is None:
        print("Error: Could not automatically locate the account index. Try passing it as an argument: python export_lighter_data.py <account_index>")
        sys.exit(1)
        
    print(f"\nTarget Account Index located: {account_index}")
    
    # 2. Generate Auth Token offline
    print("Generating secure auth token offline...")
    auth_token = generate_auth_token_offline(account_index)
    print(f"Auth token generated successfully: {auth_token[:30]}...")
    
    # 3. Request Export and Download
    try:
        data_url = trigger_export(account_index, auth_token, "trade", market_id=0)
        output_file = f"data/lighter_export_trades_acc_{account_index}.csv"
        download_file(data_url, output_file)
    except Exception as e:
        print(f"Failed to export trades: {e}")
        
    try:
        data_url = trigger_export(account_index, auth_token, "funding", market_id=0)
        output_file = f"data/lighter_export_funding_acc_{account_index}.csv"
        download_file(data_url, output_file)
    except Exception as e:
        print(f"Failed to export funding: {e}")

if __name__ == "__main__":
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_pipeline())
