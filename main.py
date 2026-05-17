import signal
import sys
import shutil
import subprocess
from database import Database
from worker_discovery import WorkerDiscovery
from cli import CLI

current_slice = {"id": None, "user": None, "orchestrator": None}
db_path = "database.yaml"
db_backup = "database.yaml.backup"
workers = ["10.0.0.1", "10.0.0.2", "10.0.0.3"]

def cleanup_workers():
    """Fast cleanup - direct SSH commands"""
    for worker in workers:
        subprocess.run(f"ssh ubuntu@{worker} 'sudo pkill -9 qemu-system-x86_64 2>/dev/null'", shell=True, timeout=3, capture_output=True)
        subprocess.run(f"ssh ubuntu@{worker} 'sudo ip link del $(sudo ip link show | grep tap | awk \"{{print \\$2}}\" | tr -d \":\") 2>/dev/null'", shell=True, timeout=3, capture_output=True)
        subprocess.run(f"ssh ubuntu@{worker} 'sudo iptables -t nat -F POSTROUTING 2>/dev/null'", shell=True, timeout=3, capture_output=True)
        subprocess.run(f"ssh ubuntu@{worker} 'sudo iptables -F FORWARD 2>/dev/null'", shell=True, timeout=3, capture_output=True)

def cleanup_local():
    subprocess.run("rm -f database.yaml.backup *.qcow2 *.iso 2>/dev/null", shell=True)

def signal_handler(sig, frame):
    print("\n🔄 Rollback...")
    if current_slice["id"] and current_slice["orchestrator"]:
        try:
            current_slice["orchestrator"].delete_slice(current_slice["user"], current_slice["id"])
        except:
            pass
    cleanup_workers()
    try:
        shutil.copy(db_backup, db_path)
    except:
        pass
    cleanup_local()
    print("✅ Done\n")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":
    try:
        shutil.copy(db_path, db_backup)
    except:
        pass
    
    db = Database()
    from remote_executor import RemoteExecutor
    executor = RemoteExecutor()
    discovery = WorkerDiscovery(executor)
    discovery.discover_all(db)
    
    cli = CLI()
    cli.current_slice = current_slice
    cli.run()
