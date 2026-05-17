import signal
import sys
from remote_executor import RemoteExecutor
from database import Database
from worker_discovery import WorkerDiscovery
from cli import CLI

# Global state for rollback
current_slice = {"id": None, "user": None, "orchestrator": None}

def signal_handler(sig, frame):
    if current_slice["id"] and current_slice["orchestrator"]:
        print(f"\n\n🔄 Rolling back slice {current_slice['id']}...")
        success, msg = current_slice["orchestrator"].delete_slice(current_slice["user"], current_slice["id"])
        print(f"✅ Rollback complete: {msg}")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":
    # Initialize worker discovery
    db = Database()
    executor = RemoteExecutor()
    discovery = WorkerDiscovery(executor)
    discovery.discover_all(db)
    
    # Start CLI
    cli = CLI()
    cli.current_slice = current_slice
    cli.run()
