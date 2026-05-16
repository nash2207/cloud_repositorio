import hashlib, logging, sys
from database import Database
from remote_executor import RemoteExecutor
from deployment_api import DeploymentAPI
from vlan_manager import VLANManager
from routing_manager import RoutingManager
from orchestrator_api import OrchestratorAPI
from health_monitor import HealthMonitor

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

db = Database()
executor = RemoteExecutor()
deployment = DeploymentAPI(executor)
vlan_mgr = VLANManager(executor)
routing_mgr = RoutingManager(executor)
orchestrator = OrchestratorAPI(db, deployment, vlan_mgr, routing_mgr)
monitor = HealthMonitor(db)

class CLI:
    def __init__(self):
        self.current_user = None
        self.current_slice = {"id": None, "user": None, "orchestrator": None}
    
    def hash_password(self, pwd):
        return hashlib.sha256(pwd.encode()).hexdigest()
    
    def login_menu(self):
        print("\n" + "="*50)
        print("  SLICE MANAGER - LOGIN")
        print("="*50)
        username = input("Username: ").strip()
        password = input("Password: ").strip()
        user = db.get_user(username)
        if user and user.get("password_hash") == self.hash_password(password):
            self.current_user = username
            print(f"\nWelcome, {username}!")
            return True
        else:
            print("\nInvalid credentials!")
            return False
    
    def main_menu(self):
        while True:
            print("\n" + "="*50)
            print("  MAIN MENU")
            print("="*50)
            print("1. View quota and resources")
            print("2. Create slice (Linear/Ring)")
            print("3. View my slices")
            print("4. Delete slice")
            print("5. Logout")
            choice = input("\nChoice: ").strip()
            if choice == "1":
                self.view_quota()
            elif choice == "2":
                self.create_slice_menu()
            elif choice == "3":
                self.view_slices()
            elif choice == "4":
                self.delete_slice_menu()
            elif choice == "5":
                self.current_user = None
                break
    
    def view_quota(self):
        user = db.get_user(self.current_user)
        if user:
            print(f"\nQuota: {user.get('used_vms', 0)}/{user.get('quota_vms', 10)} VMs used")
            print(f"Slices: {len(user.get('slices', []))}")
    
    def create_slice_menu(self):
        slice_name = input("\nSlice name: ").strip()
        num_vms = int(input("Number of VMs: ").strip())
        topology = input("Topology (linear/ring) [linear]: ").strip() or "linear"
        
        vlan_ids = [db.get_next_vlan_id(), db.get_next_vlan_id()]
        vlan_config = {
            "vlan_ids": vlan_ids,
            "topology": topology,
            "vlans": [
                {"id": vlan_ids[0], "cidr": "192.168.0.0/24", "gateway": "192.168.0.1", "dhcp": False, "internet": True},
                {"id": vlan_ids[1], "cidr": "192.168.2.0/24", "gateway": "192.168.2.1", "dhcp": True, "internet": False}
            ]
        }
        
        success, result = orchestrator.create_slice_with_vlans(self.current_user, slice_name, num_vms, vlan_config, base_image_path="/tmp/cirros.img")
        if success:
            self.current_slice["id"] = result['slice_id']
            self.current_slice["user"] = self.current_user
            self.current_slice["orchestrator"] = orchestrator
            print(f"\nSlice created! ID: {result['slice_id']}")
        else:
            print(f"\nError: {result}")
    
    def view_slices(self):
        slices = db.get_all_slices_for_user(self.current_user)
        if not slices:
            print("\nNo slices found.")
            return
        for s in slices:
            print(f"\nSlice {s['slice_id']}: {s['status']} ({len(s.get('vms', []))} VMs)")
            for vm in s.get("vms", []):
                print(f"  - {vm['name']} (VNC: {vm['vnc_port']}) @ {vm['worker_ip']}")
    
    def delete_slice_menu(self):
        slice_id = int(input("\nSlice ID: ").strip())
        success, msg = orchestrator.delete_slice(self.current_user, slice_id)
        print(f"\n{msg}")
    
    def run(self):
        monitor.start()
        while True:
            if not self.current_user:
                if not self.login_menu():
                    continue
            self.main_menu()
        monitor.stop()

if __name__ == "__main__":
    cli = CLI()
    cli.run()
