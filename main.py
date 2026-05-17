import signal, sys, shutil, subprocess
from database import Database
from remote_executor import RemoteExecutor
from worker_discovery import WorkerDiscovery
from cli import CLI

db = Database()
workers = db.data.get("workers_list", ["10.0.10.1", "10.0.10.2", "10.0.10.3"])

current_slice = {"id": None, "user": None, "orchestrator": None}
db_path = "database.yaml"
db_backup = "database.yaml.backup"

def cleanup_workers():
    for w in workers:
        subprocess.run(f"ssh -o BatchMode=yes ubuntu@{w} 'sudo pkill -9 qemu-system-x86_64 2>/dev/null'", 
                      shell=True, timeout=5, capture_output=True)

def cleanup_local():
    subprocess.run("rm -f database.yaml.backup *.qcow2 *.iso 2>/dev/null", shell=True)

def signal_handler(sig, frame):
    print("\n🔄 Rollback...")
    if current_slice["id"] and current_slice["orchestrator"]:
        try:
            current_slice["orchestrator"].delete_slice(current_slice["user"], current_slice["id"])
        except: pass
    cleanup_workers()
    try: shutil.copy(db_backup, db_path)
    except: pass
    cleanup_local()
    print("✅ Done\n")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":
    try: shutil.copy(db_path, db_backup)
    except: pass
    
    executor = RemoteExecutor()
    discovery = WorkerDiscovery(executor, workers)
    discovery.discover_all(db)
    
    cli = CLI()
    cli.current_slice = current_slice
    cli.run()
