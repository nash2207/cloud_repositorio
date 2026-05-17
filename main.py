import signal
import sys
import shutil
import subprocess
from remote_executor import RemoteExecutor
from database import Database
from worker_discovery import WorkerDiscovery
from cli import CLI

current_slice = {"id": None, "user": None, "orchestrator": None}
db_path = "database.yaml"
db_backup = "database.yaml.backup"
workers = ["10.0.0.1", "10.0.0.2", "10.0.0.3"]
executor = RemoteExecutor()

def cleanup_workers():
    """Complete cleanup on all workers"""
    for worker in workers:
        print(f"  🔴 Cleaning {worker}...")
        try:
            executor.execute(worker, "", args=["""
                sudo pkill -9 qemu-system-x86_64 || true
                for tap in $(sudo ip link show | grep tap | awk '{print $2}' | tr -d ':'); do
                    sudo ip link delete $tap 2>/dev/null || true
                done
                for ns in $(sudo ip netns list | grep -E '^ns_|^ns-'); do
                    sudo ip netns delete $ns 2>/dev/null || true
                done
                sudo iptables -t nat -F POSTROUTING || true
                sudo iptables -F FORWARD || true
                sudo iptables -P FORWARD ACCEPT || true
                for gw in $(sudo ip link show | grep gw_vlan | awk '{print $2}' | tr -d ':'); do
                    sudo ip link delete $gw 2>/dev/null || true
                done
                sudo rm -f /tmp/vm_images/*.qcow2 2>/dev/null || true
                sudo rm -f /tmp/seed_*.iso 2>/dev/null || true
            """])
        except Exception as e:
            print(f"    ⚠️  Error: {e}")

def cleanup_local():
    """Cleanup local files"""
    subprocess.run("rm -f database.yaml.backup *.qcow2 *.iso 2>/dev/null; rm -rf topologias/* 2>/dev/null", shell=True)

def signal_handler(sig, frame):
    print(f"\n\n🔄 CTRL+C detected - Rolling back completely...")
    
    # 1. Rollback slice from orchestrator
    if current_slice["id"] and current_slice["orchestrator"]:
        try:
            current_slice["orchestrator"].delete_slice(current_slice["user"], current_slice["id"])
        except:
            pass
    
    # 2. Aggressive cleanup on workers
    cleanup_workers()
    
    # 3. Restore database.yaml
    try:
        shutil.copy(db_backup, db_path)
        print("✅ database.yaml restored")
    except:
        pass
    
    # 4. Cleanup local files
    cleanup_local()
    
    print("✅ Rollback complete - all clean\n")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":
    shutil.copy(db_path, db_backup)
    print("📦 Backup created\n")
    
    db = Database()
    discovery = WorkerDiscovery(executor)
    discovery.discover_all(db)
    
    cli = CLI()
    cli.current_slice = current_slice
    cli.run()
