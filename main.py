import signal
import sys
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
    cli = CLI()
    cli.current_slice = current_slice 
    from worker_discovery import WorkerDiscovery

    discovery = WorkerDiscovery(cli.executor)    
    discovery.discover_all(cli.db)
    cli.run()