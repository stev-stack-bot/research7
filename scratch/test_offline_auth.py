import ctypes
import os
import time

# Load the shared library
lib_path = "/usr/local/lib/python3.12/dist-packages/lighter/signers/lighter-signer-linux-amd64.so"
signer = ctypes.CDLL(lib_path)

# Define StrOrErr structure
class StrOrErr(ctypes.Structure):
    _fields_ = [('str', ctypes.c_void_p), ('err', ctypes.c_void_p)]

# Set up argtypes and restype
signer.CreateClient.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_longlong]
signer.CreateClient.restype = ctypes.c_void_p

signer.CreateAuthToken.argtypes = [ctypes.c_longlong, ctypes.c_int, ctypes.c_longlong]
signer.CreateAuthToken.restype = StrOrErr

signer.Free.argtypes = [ctypes.c_void_p]
signer.Free.restype = None

def decode_and_free(ptr):
    if not ptr:
        return None
    try:
        c_str = ctypes.cast(ptr, ctypes.c_char_p).value
        if c_str is not None:
            return c_str.decode('utf-8')
        return None
    finally:
        signer.Free(ptr)

def main():
    url = "https://mainnet.zklighter.elliot.ai"
    api_key_private = "656709f6a5aae04da05425bd4c1a2239f92f1acc897586b1cd0afcb115abb89e9836531a2a21ea58"
    api_key_index = 67
    account_index = 12345  # Dummy account index to test generation
    
    print("Initializing client offline...")
    err_ptr = signer.CreateClient(
        url.encode('utf-8'),
        api_key_private.encode('utf-8'),
        304,
        api_key_index,
        account_index
    )
    err = decode_and_free(err_ptr)
    if err:
        print(f"Error creating client: {err}")
        return

    print("Generating auth token...")
    timestamp = int(time.time())
    deadline = 3600
    result = signer.CreateAuthToken(timestamp + deadline, api_key_index, account_index)
    auth = decode_and_free(result.str)
    error = decode_and_free(result.err)
    print(f"Auth Token: {auth}")
    print(f"Error: {error}")

if __name__ == "__main__":
    main()
