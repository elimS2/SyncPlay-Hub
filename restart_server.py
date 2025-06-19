#!/usr/bin/env python3
"""
Automatic web player restart script
Stops current server process and starts a new one
"""

import os
import sys
import time
import signal
import psutil
import subprocess
import argparse
import datetime
from pathlib import Path


def find_server_processes():
    """Find all Python processes running web_player.py"""
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] == 'python.exe' or proc.info['name'] == 'python':
                cmdline = proc.info['cmdline']
                if cmdline and any('web_player.py' in arg for arg in cmdline):
                    processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return processes


def stop_server():
    """Stop all server processes"""
    processes = find_server_processes()
    if not processes:
        print("🔍 No active server processes found")
        return
    
    print(f"🛑 Found {len(processes)} server process(es). Stopping...")
    
    for proc in processes:
        try:
            print(f"   Stopping process {proc.pid}")
            proc.terminate()
        except psutil.NoSuchProcess:
            continue
    
    # Give time for graceful shutdown
    time.sleep(2)
    
    # Force kill if not terminated
    for proc in processes:
        try:
            if proc.is_running():
                print(f"   Force killing process {proc.pid}")
                proc.kill()
        except psutil.NoSuchProcess:
            continue
    
    print("✅ All server processes stopped")


def start_server(root_dir, host, port):
    """Start new server process"""
    print(f"🚀 Starting server...")
    print(f"   Root: {root_dir}")
    print(f"   Host: {host}")
    print(f"   Port: {port}")
    
    cmd = [
        sys.executable, 
        "web_player.py", 
        "--root", str(root_dir),
        "--host", host,
        "--port", str(port)
    ]
    
    try:
        # Start in new process
        if os.name == 'nt':  # Windows
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:  # Unix/Linux/Mac
            subprocess.Popen(cmd)
        
        print("✅ Server started!")
        print(f"🌐 Available at: http://{host}:{port}")
        
    except Exception as e:
        print(f"❌ Server start error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Web player restart utility")
    parser.add_argument("--root", default=r"D:\music\Youtube", help="Root folder")
    parser.add_argument("--host", default="0.0.0.0", help="Server host")
    parser.add_argument("--port", type=int, default=8000, help="Server port")
    parser.add_argument("--stop-only", action="store_true", help="Only stop the server")
    
    args = parser.parse_args()
    
    print("🔄 Web Player Restart")
    print("=" * 40)
    print(f"⏰ Restart initiated at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📋 Current restart script PID: {os.getpid()}")
    
    # Stop server
    stop_server()
    
    if args.stop_only:
        print("🛑 Server stopped (--stop-only)")
        return
    
    # Small pause between stop and start
    time.sleep(1)
    
    # Start server
    start_server(args.root, args.host, args.port)
    
    print("=" * 40)
    print("✨ Restart completed!")


if __name__ == "__main__":
    main() 