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

def cleanup_network_node():
    """Cleanup all DHCP namespaces and VLANs on network node"""
    network_node = "10.0.10.3"
    cleanup_cmd = """
    # Kill all dnsmasq processes in namespaces
    for ns in $(ip netns list | grep 'ns-dhcp-vlan' | awk '{print $1}'); do
        sudo ip netns exec $ns pkill dnsmasq 2>/dev/null || true
        sudo ip netns delete $ns 2>/dev/null || true
    done
    
    # Remove all VLAN gateways and DHCP ports
    for port in $(sudo ovs-vsctl list-ports br-int | grep -E 'gw_vlan|dhcp_v'); do
        sudo ovs-vsctl del-port br-int $port 2>/dev/null || true
    done
    """
    subprocess.run(f"ssh -o BatchMode=yes ubuntu@{network_node} '{cleanup_cmd}'", 
                  shell=True, timeout=10, capture_output=True)

def cleanup_local():
    subprocess.run("rm -f database.yaml.backup *.qcow2 *.iso 2>/dev/null", shell=True)

def signal_handler(sig, frame):
    print("\n🔄 Rollback...")
    if current_slice["id"] and current_slice["orchestrator"]:
        try:
            current_slice["orchestrator"].delete_slice(current_slice["user"], current_slice["id"])
        except: pass
    cleanup_workers()
    cleanup_network_node()
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
