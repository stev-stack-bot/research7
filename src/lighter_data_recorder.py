import asyncio
import gzip
import os
import queue
import random
import signal
import sys
import time
import shutil
import threading
import websockets

# Try importing high-performance orjson, fallback to standard json
try:
    import orjson
    def json_loads(data):
        return orjson.loads(data)
except ImportError:
    import json
    def json_loads(data):
        return json.loads(data)

# Try importing high-performance zstandard compression, fallback to gzip
try:
    import zstandard as zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False

# Configuration Constants
DEFAULT_ROTATION_INTERVAL_SECS = 3600  # 1 hour
DEFAULT_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
DEFAULT_RETENTION_DAYS = 14  # 14 days
DEFAULT_FLUSH_INTERVAL_SECS = 5  # 5 seconds
QUEUE_MAX_SIZE = 1000  # Strictly capped queue size for 1 GB RAM
BATCH_MAX_SIZE = 100  # Bounded batch size for CPU/Disk smoothing
COMPRESSION_QUEUE_MAX_SIZE = 100  # Capped compression task queue

# Global bounded compression queue and worker to throttle CPU utilization to exactly 1 core
COMPRESSION_QUEUE = queue.Queue(maxsize=COMPRESSION_QUEUE_MAX_SIZE)

# Global list of active RotatableLogWriter instances
ACTIVE_WRITERS = []
ACTIVE_WRITERS_LOCK = threading.Lock()

def compression_worker():
    """Background worker thread that processes file compression tasks sequentially."""
    while True:
        task = COMPRESSION_QUEUE.get()
        if task is None:
            COMPRESSION_QUEUE.task_done()
            break

        uncompressed_path, callback = task

        # Adaptive delay: yield between files only if backlog is clear
        if COMPRESSION_QUEUE.qsize() == 0:
            time.sleep(1.0)

        if HAS_ZSTD:
            # Rotated files end in .rot. They are compressed to .jsonl.zst
            zst_path = uncompressed_path.replace(".rot", ".jsonl.zst")
            try:
                cctx = zstd.ZstdCompressor(level=3)  # Fast level 3 compression
                with open(uncompressed_path, "rb") as f_in:
                    with open(zst_path, "wb") as f_out:
                        # Wrap f_out in compressor stream
                        with cctx.stream_writer(f_out) as compressor:
                            while True:
                                # Adaptive yielding: throttle if any active writer queue is stressed (>50% full)
                                ingestion_stressed = False
                                with ACTIVE_WRITERS_LOCK:
                                    for w in ACTIVE_WRITERS:
                                        if w.queue.qsize() > int(QUEUE_MAX_SIZE * 0.5):
                                            ingestion_stressed = True
                                            break
                                if ingestion_stressed:
                                    time.sleep(0.1)

                                chunk = f_in.read(256 * 1024)
                                if not chunk:
                                    break
                                compressor.write(chunk)
                os.remove(uncompressed_path)
                log(f"Successfully compressed rotated file (Zstd): {zst_path}")
                if callback:
                    callback(uncompressed_path, zst_path)
            except Exception as e:
                log(f"Failed to compress {uncompressed_path} (Zstd): {e}", is_error=True)
            finally:
                COMPRESSION_QUEUE.task_done()
        else:
            # Rotated files end in .rot. They are compressed to .jsonl.gz
            gz_path = uncompressed_path.replace(".rot", ".jsonl.gz")
            try:
                with open(uncompressed_path, "rb") as f_in:
                    # Gzip level 1 is extremely fast, saving CPU cycles on 1 vCPU
                    with gzip.open(gz_path, "wb", compresslevel=1) as f_out:
                        while True:
                            # Adaptive yielding: throttle if any active writer queue is stressed (>50% full)
                            ingestion_stressed = False
                            with ACTIVE_WRITERS_LOCK:
                                for w in ACTIVE_WRITERS:
                                    if w.queue.qsize() > int(QUEUE_MAX_SIZE * 0.5):
                                        ingestion_stressed = True
                                        break
                            if ingestion_stressed:
                                time.sleep(0.1)

                            chunk = f_in.read(256 * 1024)
                            if not chunk:
                                break
                            f_out.write(chunk)
                os.remove(uncompressed_path)
                log(f"Successfully compressed rotated file (Gzip lvl1): {gz_path}")
                if callback:
                    callback(uncompressed_path, gz_path)
            except Exception as e:
                log(f"Failed to compress {uncompressed_path} (Gzip): {e}", is_error=True)
            finally:
                COMPRESSION_QUEUE.task_done()


def log(message: str, is_error: bool = False):
    """Prints a message with a timestamp to stdout or stderr."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    file_dest = sys.stderr if is_error else sys.stdout
    print(f"[{timestamp}] {message}", file=file_dest)


class RotatableLogWriter:
    """Thread-safe and async-buffered log writer that writes to active files,

    rotates them, and cleans up historical logs.
    Uses separate Locks for file operations and metadata indexes to eliminate lock contention.
    """
    def __init__(
        self,
        directory: str,
        file_prefix: str,
        suffix: str = ".jsonl",
        rotation_interval: int = DEFAULT_ROTATION_INTERVAL_SECS,
        max_size: int = DEFAULT_MAX_FILE_SIZE_BYTES,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        max_dir_size: int = 1500 * 1024 * 1024  # default to 1.5 GB per feed
    ):
        self.directory = directory
        self.file_prefix = file_prefix
        self.suffix = suffix
        self.rotation_interval = rotation_interval
        self.max_size = max_size
        self.retention_days = retention_days
        self.max_dir_size = max_dir_size

        self.file = None
        self.current_path = None
        self.bytes_written = 0
        self.last_rotated = time.time()

        # Diagnostic message counters & lag tracking
        self.total_messages_written = 0
        self.closed = False
        self.max_lag = 0.0

        # Unique sentinel object to prevent collision with payload data
        self.SHUTDOWN_SENTINEL = object()

        # Split Lock design to prevent contention
        self.write_lock = threading.RLock()  # Protects active file handles & rotation operations
        self.metadata_lock = threading.Lock()  # Protects historical log index dictionary

        # In-memory O(1) index dictionary of historical files
        self.managed_files = {}

        os.makedirs(self.directory, exist_ok=True)
        # Call initialization procedures directly; no other thread has a reference to this object yet.
        self._open_new_file()
        self._scan_directory_startup()

        # Dedicated Thread-safe Queue & Long-lived background OS thread
        self.queue = queue.Queue(maxsize=QUEUE_MAX_SIZE)
        self.thread = threading.Thread(target=self._thread_worker, daemon=True)
        self.thread.start()

        # Thread-safely register this writer in the active writer list
        with ACTIVE_WRITERS_LOCK:
            ACTIVE_WRITERS.append(self)

    def update_lag(self, lag_sec: float):
        """Thread-safely updates the rolling ingestion lag metrics."""
        if lag_sec > self.max_lag:
            self.max_lag = lag_sec

    def _open_new_file(self):
        """Opens a new active log file, rotating existing ones if they exceed constraints."""
        with self.write_lock:
            if self.file:
                self.file.close()

            self.current_path = os.path.join(self.directory, f"{self.file_prefix}_active{self.suffix}")

            # If active file already exists (from a previous session/crash), check size
            if os.path.exists(self.current_path):
                self.bytes_written = os.path.getsize(self.current_path)
                if self.bytes_written >= self.max_size:
                    self._rotate_sync_in_thread()
                    return
            else:
                self.bytes_written = 0

            # Open file in binary mode "ab" to bypass text encoding overhead
            self.file = open(self.current_path, "ab")
            self.last_rotated = time.time()

    def _scan_directory_startup(self):
        """Scans directory on startup. Tracks historical logs and enqueues uncompressed logs from previous crashes."""
        with self.metadata_lock:
            self.managed_files = {}
            for filename in os.listdir(self.directory):
                filepath = os.path.join(self.directory, filename)

                # 1. Startup Recovery: Detect uncompressed rotated logs (.rot suffix)
                if filename.startswith(self.file_prefix) and filename.endswith(".rot"):
                    log(f"Startup Recovery: Leftover uncompressed rotated log found: {filename}. Enqueuing...")
                    COMPRESSION_QUEUE.put((filepath, self._register_compressed_file))
                    continue

                # 2. Track already compressed files (.gz or .zst suffix)
                if filename.startswith(self.file_prefix) and (filename.endswith(".gz") or filename.endswith(".zst")):
                    try:
                        mtime = os.path.getmtime(filepath)
                        size = os.path.getsize(filepath)
                        self.managed_files[filepath] = {"mtime": mtime, "size": size}
                    except Exception as e:
                        log(f"Error scanning {filepath} on startup: {e}", is_error=True)

    async def write(self, line: bytes):
        """Pushes bytes to the write queue. Blocks strictly (applying backpressure) if the queue is full.

        Applies adaptive queue throttling when the buffer capacity exceeds 70%.
        """
        if self.closed:
            return

        # Strict parameter check to prevent double-encoding/corruption bugs
        if not isinstance(line, (bytes, bytearray)):
            raise TypeError("RotatableLogWriter.write expects bytes or bytearray")

        q_size = self.queue.qsize()
        # Proactive CPU yield backpressure under queue stress (>70% capacity)
        if q_size > int(QUEUE_MAX_SIZE * 0.7):
            await asyncio.sleep(0.001)

        while True:
            try:
                # Fast-path non-blocking call when the queue has space
                self.queue.put_nowait(line)
                break
            except queue.Full:
                # Hard backpressure: yield control to event loop cooperative multitasking (2ms sleep)
                await asyncio.sleep(0.002)

    def _thread_worker(self):
        """Dedicated background thread task consuming queue items and writing them to disk."""
        while True:
            try:
                # Check for queue items periodically
                line = self.queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if line is self.SHUTDOWN_SENTINEL:
                break

            lines = [line]

            # Retrieve any additional items currently in the queue to write in a batch
            while len(lines) < BATCH_MAX_SIZE:
                try:
                    extra_line = self.queue.get_nowait()
                    if extra_line is self.SHUTDOWN_SENTINEL:
                        # Re-queue the sentinel so we exit on the next loop
                        self.queue.put(self.SHUTDOWN_SENTINEL)
                        break
                    lines.append(extra_line)
                except queue.Empty:
                    break

            self._write_batch_to_disk(lines)

    def _write_batch_to_disk(self, lines: list):
        """Synchronously writes a batch of lines to disk under write lock."""
        # Join bytes outside lock to keep lock holding time to microseconds
        combined_data = b"".join(lines)
        with self.write_lock:
            if not self.file:
                self._open_new_file()

            try:
                self.file.write(combined_data)
                self.bytes_written += len(combined_data)
                self.total_messages_written += len(lines)
            except Exception as e:
                log(f"File write exception on prefix {self.file_prefix}: {e}", is_error=True)

            now = time.time()
            if (self.bytes_written >= self.max_size) or (now - self.last_rotated >= self.rotation_interval):
                self._rotate_sync_in_thread()

    def _rotate_sync_in_thread(self):
        """Rotates the active file under write lock, flushing & syncing data before compressing in a thread."""
        with self.write_lock:
            old_path = self.current_path
            if self.file:
                try:
                    # Flush Python buffers and force write to NVMe device to prevent log corruption
                    self.file.flush()
                    os.fsync(self.file.fileno())
                except Exception as e:
                    log(f"Error syncing file {old_path} before rotation: {e}", is_error=True)
                self.file.close()
                self.file = None

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            # State-safe name ending in .rot
            rotated_path = os.path.join(self.directory, f"{self.file_prefix}_{timestamp}.rot")

            # Avoid naming collisions
            counter = 1
            while os.path.exists(rotated_path):
                rotated_path = os.path.join(self.directory, f"{self.file_prefix}_{timestamp}_{counter}.rot")
                counter += 1

            if os.path.exists(old_path):
                try:
                    os.rename(old_path, rotated_path)

                    # Register the .rot file immediately in managed_files for correct disk accounting
                    with self.metadata_lock:
                        mtime = os.path.getmtime(rotated_path)
                        size = os.path.getsize(rotated_path)
                        self.managed_files[rotated_path] = {"mtime": mtime, "size": size}

                    # Enqueue file compression task to the global worker queue
                    COMPRESSION_QUEUE.put((rotated_path, self._register_compressed_file))
                except Exception as e:
                    log(f"Error rotating file {old_path}: {e}", is_error=True)

            self._open_new_file()

    def _register_compressed_file(self, old_path: str, gz_path: str):
        """Thread-safely registers the compressed file and removes the uncompressed .rot record."""
        with self.metadata_lock:
            try:
                self.managed_files.pop(old_path, None)
                if os.path.exists(gz_path):
                    mtime = os.path.getmtime(gz_path)
                    size = os.path.getsize(gz_path)
                    self.managed_files[gz_path] = {"mtime": mtime, "size": size}
            except Exception as e:
                log(f"Error registering compressed file {gz_path}: {e}", is_error=True)

    async def flush(self):
        """Triggers thread-safe file flush from event loop."""
        await asyncio.to_thread(self._flush_sync)

    def _flush_sync(self):
        """Synchronously flushes the file (OS write cache handles durability, fsync only on rotation/close)."""
        with self.write_lock:
            if self.file:
                try:
                    self.file.flush()
                except Exception as e:
                    log(f"Error flushing {self.file_prefix}: {e}", is_error=True)

    async def close(self):
        """Gracefully shuts down the writer, draining outstanding queue items completely first."""
        self.closed = True

        # Remove this writer from the active registry list upon closure
        with ACTIVE_WRITERS_LOCK:
            if self in ACTIVE_WRITERS:
                ACTIVE_WRITERS.remove(self)

        # 1. Put unique sentinel in the queue to signal worker thread termination (after processing remaining items)
        try:
            self.queue.put(self.SHUTDOWN_SENTINEL)
        except Exception:
            pass

        # 2. Wait for the background thread to finish draining and join
        try:
            await asyncio.to_thread(self.thread.join, timeout=10.0)
        except Exception as e:
            log(f"Error joining dedicated writer thread for {self.file_prefix}: {e}", is_error=True)

        # 3. Sync close file handle
        await asyncio.to_thread(self._close_sync)

    def _close_sync(self):
        """Synchronously closes and fsyncs the file handle. Run inside thread pools."""
        with self.write_lock:
            if self.file:
                try:
                    self.file.flush()
                    os.fsync(self.file.fileno())
                except Exception as e:
                    log(f"Error syncing file during close: {e}", is_error=True)
                self.file.close()
                self.file = None

    async def cleanup_old_files(self):
        """Triggers log cleanup from event loop."""
        await asyncio.to_thread(self._cleanup_old_files_sync)

    def _cleanup_old_files_sync(self):
        """Removes expired and limit-exceeding logs based on the in-memory managed_files list."""
        now = time.time()
        retention_seconds = self.retention_days * 86400
        files_to_delete = []

        with self.metadata_lock:
            # 1. Filter out files that are too old or don't exist
            for filepath, meta in list(self.managed_files.items()):
                if not os.path.exists(filepath):
                    self.managed_files.pop(filepath, None)
                    continue

                age = now - meta["mtime"]
                if age > retention_seconds:
                    files_to_delete.append(filepath)

            # 2. Enforce total directory size limit
            total_size = sum(meta["size"] for meta in self.managed_files.values())

            if total_size > self.max_dir_size:
                sorted_files = sorted(self.managed_files.items(), key=lambda x: x[1]["mtime"])
                for oldest_file, meta in sorted_files:
                    if total_size <= self.max_dir_size:
                        break
                    if oldest_file not in files_to_delete:
                        files_to_delete.append(oldest_file)
                        total_size -= meta["size"]

            # 3. Emergency Disk Watermark Enforcement
            # Ensure at least 10% of total disk space or 1.5 GB remains free
            try:
                total_disk, used_disk, free_disk = shutil.disk_usage(self.directory)
                safety_limit_bytes = max(total_disk * 0.1, 1500 * 1024 * 1024)
                if free_disk < safety_limit_bytes:
                    free_gb = free_disk / (1024 * 1024 * 1024)
                    limit_gb = safety_limit_bytes / (1024 * 1024 * 1024)
                    log(f"CRITICAL: Free disk space is low ({free_gb:.2f} GB free, threshold {limit_gb:.2f} GB). Triggering emergency log purge...", is_error=True)
                    sorted_files = sorted(self.managed_files.items(), key=lambda x: x[1]["mtime"])
                    for oldest_file, meta in sorted_files:
                        if free_disk >= safety_limit_bytes:
                            break
                        if oldest_file not in files_to_delete:
                            files_to_delete.append(oldest_file)
                            free_disk += meta["size"]
            except Exception as disk_err:
                log(f"Failed to query disk usage during cleanup: {disk_err}", is_error=True)

        # --- Perform physical deletions OUTSIDE the lock to prevent blocking writes ---
        deleted_paths = []
        for filepath in files_to_delete:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                    log(f"Cleaned up file: {filepath}")
                deleted_paths.append(filepath)
            except FileNotFoundError:
                deleted_paths.append(filepath)
            except Exception as e:
                log(f"Error removing file {filepath} outside lock: {e}", is_error=True)

        # --- Re-acquire lock to update the index dictionary ---
        with self.metadata_lock:
            for filepath in deleted_paths:
                self.managed_files.pop(filepath, None)


async def flush_timer(writers: list):
    """Periodically flushes list of RotatableLogWriter writers to avoid losing data on crash."""
    while True:
        try:
            await asyncio.sleep(DEFAULT_FLUSH_INTERVAL_SECS)
            for writer in writers:
                await writer.flush()
        except asyncio.CancelledError:
            break
        except Exception as e:
            log(f"Error in flush timer: {e}", is_error=True)


async def cleanup_timer(writers: list):
    """Periodically triggers retention cleanup to keep disk space usage in check."""
    while True:
        try:
            # Run retention scan every 30 minutes to minimize CPU and directory metadata scans
            await asyncio.sleep(1800)
            log("Running periodic log retention cleanup...")
            for writer in writers:
                await writer.cleanup_old_files()
        except asyncio.CancelledError:
            break
        except Exception as e:
            log(f"Error in cleanup timer: {e}", is_error=True)


async def metrics_timer(writers: list):
    """Periodically prints ingestion diagnostics and backpressure status logs for active writers."""
    last_time = time.time()
    last_counts = {w: w.total_messages_written for w in writers}

    while True:
        try:
            await asyncio.sleep(10)
            now = time.time()
            elapsed = now - last_time
            last_time = now

            log("--- Ingestion Metrics ---")
            for w in writers:
                current_count = w.total_messages_written
                diff = current_count - last_counts[w]
                last_counts[w] = current_count

                msg_rate = diff / elapsed if elapsed > 0 else 0
                q_size = w.queue.qsize()

                # Check status warning thresholds
                q_status = "OK"
                if q_size > QUEUE_MAX_SIZE * 0.8:
                    q_status = "CRITICAL"
                elif q_size > QUEUE_MAX_SIZE * 0.5:
                    q_status = "WARNING"

                lag_str = f"{w.max_lag:.3f}s" if w.max_lag > 0 else "N/A"
                # Reset max lag for the next period to make it a rolling metric
                w.max_lag = 0.0

                log(
                    f"[{w.file_prefix}] "
                    f"Queue: {q_size}/{QUEUE_MAX_SIZE} ({q_status}) | "
                    f"Rate: {msg_rate:.1f} msg/sec | "
                    f"Lag: {lag_str} | "
                    f"Total: {current_count} | "
                    f"Files: {len(w.managed_files)}"
                )
            log("-------------------------")
        except asyncio.CancelledError:
            break
        except Exception as e:
            log(f"Error in metrics timer: {e}", is_error=True)


async def record_feed(
    market_id: str,
    book_writer: RotatableLogWriter,
    trades_writer: RotatableLogWriter,
    shutdown_event: asyncio.Event
):
    """Main recorder loop connecting to WebSocket and logging order book/trade updates."""
    uri = "wss://mainnet.zklighter.elliot.ai/stream?readonly=true"
    retry_delay = 1
    log(f"Starting recorder for market {market_id}...")

    last_drop_warning = 0.0

    while not shutdown_event.is_set():
        # Partitioned sequence tracking reset upon connection restarts
        last_seq_by_channel = {}
        last_ws_recv_time = time.time()
        try:
            # Connect with robust ping/pong checks
            async with websockets.connect(
                uri,
                ping_interval=20,  # Ping server every 20s
                ping_timeout=20,   # Disconnect if pong not received in 20s
                close_timeout=10
            ) as websocket:
                retry_delay = 1  # Reset connection recovery timer
                log(f"Connected to Lighter WebSocket for market {market_id}")

                # Subscribe using raw strings to avoid json_loads/json.dumps() serialization
                await websocket.send(f'{{"type":"subscribe","channel":"order_book/{market_id}"}}')
                await websocket.send(f'{{"type":"subscribe","channel":"trade/{market_id}"}}')

                log(f"Subscriptions sent. Recording active for market {market_id}...")

                while not shutdown_event.is_set():
                    try:
                        message_str = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        last_ws_recv_time = time.time()

                        # Hard memory ceiling check: prevent massive messages from causing OOM
                        if len(message_str) > 1024 * 1024:
                            log(f"WARNING: Discarding excessively large message ({len(message_str)} bytes) on market {market_id} to prevent OOM.", is_error=True)
                            continue

                        # Pre-validate JSON nesting depth to prevent pathological CPU/RAM stack overflows
                        depth = 0
                        pathological = False
                        for char in message_str:
                            if char == '{':
                                depth += 1
                                if depth > 10:  # Allow up to 10 levels of nesting
                                    pathological = True
                                    break
                            elif char == '}':
                                depth -= 1
                        if pathological:
                            log(f"WARNING: Discarding pathological message structure on market {market_id} to prevent CPU/RAM saturation.", is_error=True)
                            continue

                        # Validate schemas and protect against malformed payload loop crashes
                        try:
                            msg = json_loads(message_str)
                        except Exception as parse_err:
                            log(f"JSON schema/parsing exception on market {market_id}: {parse_err}. Raw message snippet: {message_str[:200]}", is_error=True)
                            continue

                        msg_type = msg.get("type")
                        channel = msg.get("channel")

                        if not msg_type or not channel:
                            continue

                        # Channel-partitioned sequence verification (resets on reconnects)
                        seq = msg.get("sequence_id") or msg.get("sequence") or msg.get("seq")
                        if seq is None and isinstance(msg.get("data"), dict):
                            data_payload = msg["data"]
                            seq = data_payload.get("sequence_id") or data_payload.get("sequence") or data_payload.get("seq")

                        if seq is not None and isinstance(seq, (int, float)):
                            last_seq = last_seq_by_channel.get(channel)
                            if last_seq is not None:
                                expected = last_seq + 1
                                if seq > expected:
                                    log(
                                        f"Sequence GAP detected on market {market_id} for channel {channel}: "
                                        f"Expected {expected}, Got {seq}",
                                        is_error=True
                                    )
                            last_seq_by_channel[channel] = seq

                        ts_us = None
                        if msg_type == "update/order_book":
                            ob_data = msg.get("order_book", {})
                            if ob_data:
                                ts_us = ob_data.get("last_updated_at") or msg.get("last_updated_at")
                            if ts_us is None:
                                ts_us = msg.get("last_updated_at")
                            await book_writer.write((message_str + "\n").encode('utf-8'))
                        elif msg_type == "update/trade":
                            # Degradation Mode: drop trades if queue is saturated to preserve order book ingestion
                            if trades_writer.queue.qsize() > int(QUEUE_MAX_SIZE * 0.8):
                                now = time.time()
                                if now - last_drop_warning > 5.0:
                                    log(f"[WARNING] High queue stress on market {market_id} trades ({trades_writer.queue.qsize()}/{QUEUE_MAX_SIZE}). Dropping trade update to prevent ingestion lag.", is_error=True)
                                    last_drop_warning = now
                                continue

                            trades_list = msg.get("trades") or msg.get("data", {}).get("trades") or []
                            if trades_list:
                                ts_us = trades_list[0].get("transaction_time")
                            await trades_writer.write((message_str + "\n").encode('utf-8'))
                        elif msg_type.startswith("subscribed/"):
                            # Snapshot channel validation is done via payload string match
                            if "order_book" in msg_type or "order_book" in channel:
                                ob_data = msg.get("order_book", {})
                                if ob_data:
                                    ts_us = ob_data.get("last_updated_at") or msg.get("last_updated_at")
                                await book_writer.write((message_str + "\n").encode('utf-8'))
                                log(f"Subscription confirmed for: {channel}")

                        if ts_us is not None:
                            try:
                                lag_sec = time.time() - (float(ts_us) / 1000000.0)
                                if msg_type == "update/order_book" or ("order_book" in msg_type or "order_book" in channel):
                                    book_writer.update_lag(lag_sec)
                                elif msg_type == "update/trade":
                                    trades_writer.update_lag(lag_sec)
                            except Exception:
                                pass

                    except asyncio.TimeoutError:
                        # Feed stall detection (60s threshold resets silent socket)
                        now = time.time()
                        if now - last_ws_recv_time > 60.0:
                            log(f"Market feed stall detected on market {market_id} (60s silence). Reconnecting...", is_error=True)
                            break
                        continue

        except asyncio.CancelledError:
            log(f"Recording loop for market {market_id} cancelled.")
            break
        except Exception as e:
            if shutdown_event.is_set():
                break
            # Calculate backoff with jitter to prevent thundering herd reconnects
            jitter = random.uniform(0.0, 1.0)
            log(f"WebSocket exception for market {market_id}: {e}. Reconnecting in {retry_delay + jitter:.2f}s...", is_error=True)
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=retry_delay + jitter)
            except asyncio.TimeoutError:
                pass
            retry_delay = min(retry_delay * 2, 60)

    log(f"Recording loop for market {market_id} finished.")


async def shutdown_after(duration_sec: int, shutdown_event: asyncio.Event):
    """Triggers shutdown after a specified duration."""
    await asyncio.sleep(duration_sec)
    log(f"Requested duration limit of {duration_sec}s reached. Stopping all recording...")
    shutdown_event.set()


async def main():
    market_input = "0" if len(sys.argv) < 2 else sys.argv[1]
    duration = 0 if len(sys.argv) < 3 else int(sys.argv[2])
    out_dir = "data" if len(sys.argv) < 4 else sys.argv[3]

    # Parse market list (e.g. "0,1,2")
    market_ids = [m.strip() for m in market_input.split(",") if m.strip()]
    if not market_ids:
        market_ids = ["0"]

    os.makedirs(out_dir, exist_ok=True)

    # Start global compression worker thread
    compression_thread = threading.Thread(target=compression_worker, daemon=True)
    compression_thread.start()

    # Calculate disk safety limit per writer dynamically based on number of markets
    # Allocating a safe 9 GB total of storage for data.
    # Total writers = 2 * len(market_ids) (book and trades for each coin)
    total_writers = 2 * len(market_ids)
    max_dir_size_per_writer = int((9 * 1024 * 1024 * 1024) / total_writers)

    log(f"Initializing recorders for markets: {market_ids}")
    log(f"Allocating max storage of {max_dir_size_per_writer / (1024*1024):.1f} MB per feed (Total: 9.0 GB)")

    # Configure loop signal handlers for graceful shutdown (Unix only)
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown_event.set)
        except NotImplementedError:
            pass  # Fallback for Windows/environments without Unix signals support

    # Instantiate rotatable file writers in main
    writers = []
    market_feeds = []

    for m in market_ids:
        book_writer = RotatableLogWriter(
            out_dir,
            f"raw_lighter_book_{m}",
            rotation_interval=DEFAULT_ROTATION_INTERVAL_SECS,
            max_size=DEFAULT_MAX_FILE_SIZE_BYTES,
            retention_days=DEFAULT_RETENTION_DAYS,
            max_dir_size=max_dir_size_per_writer
        )
        trades_writer = RotatableLogWriter(
            out_dir,
            f"raw_lighter_trades_{m}",
            rotation_interval=DEFAULT_ROTATION_INTERVAL_SECS,
            max_size=DEFAULT_MAX_FILE_SIZE_BYTES,
            retention_days=DEFAULT_RETENTION_DAYS,
            max_dir_size=max_dir_size_per_writer
        )
        writers.extend([book_writer, trades_writer])
        market_feeds.append((m, book_writer, trades_writer))

    # Run initial cleanup scans
    log("Running initial log retention cleanup...")
    for writer in writers:
        await writer.cleanup_old_files()

    # Start background timers
    flush_task = asyncio.create_task(flush_timer(writers))
    cleanup_task = asyncio.create_task(cleanup_timer(writers))
    metrics_task = asyncio.create_task(metrics_timer(writers))

    shutdown_task = None
    if duration > 0:
        shutdown_task = asyncio.create_task(shutdown_after(duration, shutdown_event))

    try:
        # Run all recorders concurrently in the same process
        await asyncio.gather(*[record_feed(m, book_w, trade_w, shutdown_event) for m, book_w, trade_w in market_feeds])
    finally:
        if shutdown_task:
            shutdown_task.cancel()
            try:
                await shutdown_task
            except asyncio.CancelledError:
                pass

        # Cancel background timers
        flush_task.cancel()
        cleanup_task.cancel()
        metrics_task.cancel()
        try:
            await asyncio.gather(flush_task, cleanup_task, metrics_task, return_exceptions=True)
        except Exception:
            pass

        log("Closing all writers and flushing queues...")
        # Close all writers concurrently, draining active queues to prevent data loss
        await asyncio.gather(*[w.close() for w in writers])

        # Signal compression thread to stop and wait for final compressions to finish
        log("Waiting for pending log compressions to complete...")
        COMPRESSION_QUEUE.put(None)
        await asyncio.to_thread(compression_thread.join, timeout=10.0)

        log("All writers closed. Shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("Process terminated by user.")