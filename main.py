"""
Slice Manager - Main Entry Point
Supports CLI, Web, or both interfaces simultaneously
"""
import signal
import sys
import shutil
import subprocess
import argparse
import logging
import threading
import time

from database import Database
from remote_executor import RemoteExecutor
from worker_discovery import WorkerDiscovery
from sync_manager import SyncManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global state
db = Database()
clusters = db.data.get("clusters", {})
workers = clusters.get("linux", {}).get("workers", ["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4"])
network_node = clusters.get("linux", {}).get("network_node", "10.0.0.1")
current_slice = {"id": None, "user": None, "orchestrator": None}
db_path = "database.yaml"
db_backup = "database.yaml.backup"
web_thread = None
web_running = False


def cleanup_workers():
    """Stop all QEMU VMs on workers"""
    for w in workers:
        subprocess.run(
            f"ssh -o BatchMode=yes ubuntu@{w} 'sudo pkill -9 qemu-system-x86_64 2>/dev/null'",
            shell=True, timeout=5, capture_output=True
        )


def cleanup_network_node():
    """Cleanup all DHCP namespaces and VLANs on network node"""
    cleanup_cmd = """
    for ns in $(ip netns list | grep 'ns-dhcp-vlan' | awk '{print $1}'); do
        sudo ip netns exec $ns pkill dnsmasq 2>/dev/null || true
        sudo ip netns delete $ns 2>/dev/null || true
    done
    for port in $(sudo ovs-vsctl list-ports br-int | grep -E 'gw_vlan|dhcp_v'); do
        sudo ovs-vsctl del-port br-int $port 2>/dev/null || true
    done
    """
    try:
        subprocess.run(
            f"ssh -o BatchMode=yes ubuntu@{network_node} '{cleanup_cmd}'",
            shell=True, timeout=10, capture_output=True
        )
    except subprocess.TimeoutExpired:
        logger.warning(f"Cleanup timeout on {network_node} - continuing anyway")


def cleanup_local():
    """Cleanup local temporary files"""
    subprocess.run("rm -f database.yaml.backup *.qcow2 *.iso 2>/dev/null", shell=True)


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\n🔄 Cleaning up...")
    if current_slice["id"] and current_slice["orchestrator"]:
        try:
            current_slice["orchestrator"].delete_slice(
                current_slice["user"], 
                current_slice["id"]
            )
        except:
            pass
    
    # Stop all websockify proxies
    try:
        from vnc_proxy import vnc_proxy_manager
        vnc_proxy_manager.stop_all()
        logger.info("Stopped all VNC proxies")
    except:
        pass
    
    cleanup_workers()
    cleanup_network_node()
    cleanup_local()
    print("✅ Done\n")
    sys.exit(0)


def initialize_system():
    """Initialize database and sync workers"""
    # Backup database
    try:
        shutil.copy(db_path, db_backup)
    except:
        pass
    
    executor = RemoteExecutor()
    
    # Discover worker specs
    logger.info("Discovering workers...")
    discovery = WorkerDiscovery(executor, workers)
    discovery.discover_all(db)
    
    # Sync worker state with database
    logger.info("Synchronizing worker state...")
    sync_manager = SyncManager(db, executor)
    sync_manager.sync_all_workers()
    
    return executor


def run_cli():
    """Run CLI interface"""
    from cli import CLI
    
    logger.info("Starting CLI mode")
    cli = CLI()
    cli.current_slice = current_slice
    cli.run()


def run_web():
    """Run Web interface in background thread"""
    global web_running
    import uvicorn
    from web_api import app
    
    logger.info("Starting Web interface on http://0.0.0.0:8080")
    web_running = True
    
    # Run uvicorn in this thread
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="warning")
    server = uvicorn.Server(config)
    server.run()
    
    web_running = False


def start_web_background():
    """Start web server in background thread"""
    global web_thread
    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    
    # Wait for server to start
    time.sleep(2)
    
    print("\n" + "="*60)
    print("🌐 Web Interface Started")
    print("="*60)
    print(f"📍 Local:    http://localhost:8080")
    print(f"📍 Network:  http://0.0.0.0:8080")
    print(f"📍 External: http://<server-ip>:8080")
    print("🔑 Login with your credentials")
    print("="*60 + "\n")


def run_both():
    """Run both CLI and Web simultaneously"""
    # Start web in background
    start_web_background()
    
    # Run CLI in foreground
    print("Starting CLI interface...")
    print("(Web interface running in background)\n")
    run_cli()


def main():
    """Main entry point with mode selection"""
    parser = argparse.ArgumentParser(
        description="Slice Manager - Network Slice Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py              # Interactive mode selection
  python main.py --cli        # Start CLI only
  python main.py --web        # Start Web only
  python main.py --both       # Start both CLI and Web
        """
    )
    parser.add_argument(
        '--cli',
        action='store_true',
        help='Start in CLI mode only'
    )
    parser.add_argument(
        '--web',
        action='store_true',
        help='Start in Web mode only'
    )
    parser.add_argument(
        '--both',
        action='store_true',
        help='Start both CLI and Web simultaneously'
    )
    
    args = parser.parse_args()
    
    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    # Initialize system
    initialize_system()
    
    # Determine mode
    if args.cli:
        run_cli()
    elif args.web:
        run_web()
    elif args.both:
        run_both()
    else:
        # Interactive mode selection
        print("\n" + "="*60)
        print("🚀 Slice Manager - Network Slice Orchestrator")
        print("="*60)
        print("Select interface mode:")
        print("  1. CLI   - Command Line Interface only")
        print("  2. Web   - Web Interface only (http://0.0.0.0:8080)")
        print("  3. Both  - CLI + Web simultaneously")
        print("="*60)
        
        while True:
            choice = input("\nEnter choice (1, 2, or 3): ").strip()
            if choice == "1":
                run_cli()
                break
            elif choice == "2":
                run_web()
                break
            elif choice == "3":
                run_both()
                break
            else:
                print("❌ Invalid choice. Please enter 1, 2, or 3.")


if __name__ == "__main__":
    main()
