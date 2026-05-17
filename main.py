import signal
import sys
import shutil
import os
from remote_executor import RemoteExecutor
from database import Database
from worker_discovery import WorkerDiscovery
from cli import CLI

# Global state
current_slice = {"id": None, "user": None, "orchestrator": None}
db_backup_path = "/tmp/database.yaml.backup"
db_original_path = "/Users/markito/Desktop/cloud/lab1/database.yaml"

def signal_handler(sig, frame):
    print(f"\n\n🔄 Rolling back everything...")
    
    # Rollback slice if exists
    if current_slice["id"] and current_slice["orchestrator"]:
        try:
            current_slice["orchestrator"].delete_slice(current_slice["user"], current_slice["id"])
        except:
            pass
    
    # Restore database.yaml from backup
    if os.path.exists(db_backup_path):
        shutil.copy(db_backup_path, db_original_path)
        print("✅ database.yaml restored")
    
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":
    # Create backup of database.yaml
    shutil.copy(db_original_path, db_backup_path)
    print("📦 database.yaml backup created")
    
    # Initialize worker discovery
    db = Database()
    executor = RemoteExecutor()
    discovery = WorkerDiscovery(executor)
    discovery.discover_all(db)
    
    # Start CLI
    cli = CLI()
    cli.current_slice = current_slice
    cli.run()
