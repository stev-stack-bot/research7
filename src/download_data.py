import os
import sys
import subprocess
import getpass

def run_sync():
    print("=== VPS Data Sync Utility ===")
    host = input("Enter VPS Host IP or Domain: ").strip()
    if not host:
        print("Host cannot be empty.")
        return
        
    username = input("Enter VPS Username [root]: ").strip() or "root"
    port = input("Enter SSH Port [22]: ").strip() or "22"
    
    remote_path = input("Enter path to 'data/' folder on VPS (e.g. /home/user/data): ").strip()
    if not remote_path:
        print("Remote path cannot be empty.")
        return
        
    local_path = input("Enter local destination path [/kaggle/working/data]: ").strip() or "/kaggle/working/data"
    os.makedirs(local_path, exist_ok=True)
    
    password = getpass.getpass("Enter VPS Password: ")
    
    # Use sshpass to pass the password securely via environment variable
    env = os.environ.copy()
    env["SSHPASS"] = password
    
    # 1. Attempt rsync first (efficient, supports resume and diffs)
    # -o StrictHostKeyChecking=no avoids prompt for host key acceptance
    rsync_cmd = [
        "sshpass", "-e",
        "rsync", "-avz",
        "--progress",
        "-e", f"ssh -p {port} -o StrictHostKeyChecking=no",
        f"{username}@{host}:{remote_path}/",
        f"{local_path}/"
    ]
    
    print(f"\nAttempting rsync from {username}@{host}:{remote_path} to {local_path}...")
    try:
        result = subprocess.run(rsync_cmd, env=env)
        if result.returncode == 0:
            print("\n[SUCCESS] Sync completed successfully via rsync!")
            return
        else:
            print(f"\n[INFO] rsync returned code {result.returncode}. Attempting fallback to scp...", file=sys.stderr)
    except Exception as e:
        print(f"\n[INFO] Could not run rsync: {e}. Attempting fallback to scp...", file=sys.stderr)
        
    # 2. Fallback to scp if rsync fails or is not installed on the VPS
    scp_cmd = [
        "sshpass", "-e",
        "scp", "-P", port,
        "-o", "StrictHostKeyChecking=no",
        "-r",
        f"{username}@{host}:{remote_path}/*",
        f"{local_path}/"
    ]
    
    print(f"\nAttempting scp from {username}@{host}:{remote_path} to {local_path}...")
    try:
        result = subprocess.run(scp_cmd, env=env)
        if result.returncode == 0:
            print("\n[SUCCESS] Sync completed successfully via scp!")
        else:
            print(f"\n[ERROR] scp failed with exit code {result.returncode}.", file=sys.stderr)
    except Exception as e:
        print(f"\n[ERROR] Failed running scp: {e}", file=sys.stderr)

if __name__ == "__main__":
    run_sync()
