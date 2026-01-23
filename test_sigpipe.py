#!/usr/bin/env python
"""
Test to reproduce SIGPIPE issue on macOS.

On macOS without SO_NOSIGPIPE, writing to a closed socket
raises SIGPIPE which can crash the process.

Run this on macOS to verify the issue.
"""
import socket
import os
import sys
import signal
import time
import multiprocessing

def server_closes_early(port, ready_event, close_event):
    """Server that accepts connection then closes it abruptly."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', port))
    sock.listen(1)
    ready_event.set()

    conn, addr = sock.accept()
    print(f"[Server] Accepted connection from {addr}")

    # Close immediately without reading
    time.sleep(0.1)  # Small delay to ensure client starts sending
    print("[Server] Closing connection abruptly...")
    conn.close()
    sock.close()
    close_event.set()

def client_sends_after_close(port, ready_event, close_event):
    """Client that tries to send data after server closes."""
    ready_event.wait()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('127.0.0.1', port))
    print("[Client] Connected to server")

    # Wait for server to close
    close_event.wait()
    time.sleep(0.1)  # Ensure server has fully closed

    print("[Client] Attempting to send data to closed socket...")
    try:
        # This should trigger SIGPIPE on macOS without SO_NOSIGPIPE
        for i in range(10):
            sock.send(b"x" * 10000)
            print(f"[Client] Sent chunk {i}")
    except BrokenPipeError as e:
        print(f"[Client] Got BrokenPipeError (expected): {e}")
        return True
    except Exception as e:
        print(f"[Client] Got unexpected error: {type(e).__name__}: {e}")
        return False

    print("[Client] No error - might have SO_NOSIGPIPE or SIGPIPE ignored")
    return True

def sigpipe_handler(signum, frame):
    print(f"[SIGPIPE] Caught SIGPIPE signal! This is the bug on macOS.")
    sys.exit(1)

def main():
    print(f"Platform: {sys.platform}")
    print(f"Python: {sys.version}")

    # Check if SIGPIPE is available (not on Windows)
    if hasattr(signal, 'SIGPIPE'):
        # Don't ignore SIGPIPE - we want to see if it's raised
        # signal.signal(signal.SIGPIPE, signal.SIG_IGN)  # This would hide the bug
        signal.signal(signal.SIGPIPE, sigpipe_handler)
        print("SIGPIPE handler installed")
    else:
        print("SIGPIPE not available on this platform")

    port = 19876
    ready_event = multiprocessing.Event()
    close_event = multiprocessing.Event()

    server = multiprocessing.Process(
        target=server_closes_early,
        args=(port, ready_event, close_event)
    )
    server.start()

    # Run client in main process to catch SIGPIPE
    success = client_sends_after_close(port, ready_event, close_event)

    server.join()

    if success:
        print("\n[RESULT] Test completed - SIGPIPE was handled properly")
    else:
        print("\n[RESULT] Test had issues")

if __name__ == "__main__":
    main()
