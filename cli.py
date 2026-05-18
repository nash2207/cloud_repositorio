"""CLI Interface for Slice Manager"""
import hashlib, logging, sys
from database import Database
from remote_executor import RemoteExecutor
from deployment_api import DeploymentAPI
from orchestrator_api import OrchestratorAPI
from health_monitor import HealthMonitor

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

db = Database()
executor = RemoteExecutor()
deployment = DeploymentAPI(executor)
orchestrator = OrchestratorAPI(db, deployment)
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
            print("2. Create Slice")
            print("3. Add VM to Slice")
            print("4. Create Link between VMs")
            print("5. View my Slices")
            print("6. Deploy Slice")
            print("7. Delete Slice")
            print("8. Logout")
            choice = input("\nChoice: ").strip()
            if choice == "1":
                self.view_quota()
            elif choice == "2":
                self.create_slice_menu()
            elif choice == "3":
                self.add_vm_menu()
            elif choice == "4":
                self.create_link_menu()
            elif choice == "5":
                self.view_slices()
            elif choice == "6":
                self.deploy_slice_menu()
            elif choice == "7":
                self.delete_slice_menu()
            elif choice == "8":
                self.current_user = None
                break
    
    def view_quota(self):
        user = db.get_user(self.current_user)
        if user:
            print(f"\nQuota: {user.get('used_vms', 0)}/{user.get('quota_vms', 10)} VMs used")
    
    def create_slice_menu(self):
        slice_name = input("\nSlice name: ").strip()
        
        success, result = orchestrator.create_slice(self.current_user, slice_name)
        if success:
            self.current_slice["id"] = result.get('slice_id')
            self.current_slice["user"] = self.current_user
            self.current_slice["orchestrator"] = orchestrator
            print(f"\n✅ Slice created! ID: {result['slice_id']}")
        else:
            print(f"\n❌ Error: {result}")
    
    def add_vm_menu(self):
        slice_id = input("\nSlice ID: ").strip()
        vm_name = input("VM name: ").strip()
        
        print("\nAvailable flavors:")
        print("1. cirros (1 core, 0.5GB RAM, 1GB disk)")
        print("2. ubuntu (1 core, 0.5GB RAM, 2.2GB disk)")
        flavor_choice = input("Choose flavor (1-2): ").strip()
        
        flavors = {"1": "cirros", "2": "ubuntu"}
        flavor_name = flavors.get(flavor_choice, "cirros")
        
        data_interfaces = input("Number of data interfaces (eth1, eth2, ...): ").strip()
        data_interfaces = int(data_interfaces) if data_interfaces.isdigit() else 1
        
        internet = input("Enable internet access (eth0 in VLAN 400)? (y/n): ").strip().lower() == 'y'
        
        success, result = orchestrator.add_vm_to_slice(
            self.current_user, slice_id, vm_name, flavor_name,
            data_interfaces, internet
        )
        if success:
            print(f"\n✅ VM added! ID: {result['vm_id']}, VNC: {result['vnc_port']}, Flavor: {flavor_name}")
        else:
            print(f"\n❌ Error: {result}")
    
    def view_slices(self):
        user = db.get_user(self.current_user)
        slice_ids = user.get('slices', [])
        if not slice_ids:
            print("\nNo Slices found.")
            return
        print("\n" + "="*70)
        for slice_id in slice_ids:
            slice_data = db.get_slice(slice_id)
            if slice_data:
                vm_count = len(slice_data.get("vms", []))
                link_count = len(slice_data.get("links", []))
                status = slice_data.get("status", "design")
                vlan_pool = f"{slice_data.get('vlan_pool_start')}-{slice_data.get('vlan_pool_end')}"
                print(f"Slice {slice_id} [{status}]: {vm_count} VMs, {link_count} Links, VLAN pool: {vlan_pool}")
                for vm in slice_data.get("vms", []):
                    flavor = vm.get('flavor', {}).get('disk_gb', 'N/A')
                    print(f"  └─ VM {vm['vm_id']}: {vm['name']} (VNC: {vm['vnc_port']}, Worker: {vm['worker_ip']}, Disk: {flavor}GB)")
                    for iface in vm.get("interfaces", []):
                        link_info = f", Link: {iface['link_id']}" if iface.get('link_id') else ", unconnected"
                        vlan_info = f", VLAN: {iface['vlan_id']}" if iface.get('vlan_id') else ""
                        print(f"      {iface['name']}: MAC {iface['mac']}{vlan_info}{link_info}")
                for link in slice_data.get("links", []):
                    print(f"  Link {link['link_id']}: VM{link['vm1_id']}.{link['vm1_interface']} <-> VM{link['vm2_id']}.{link['vm2_interface']} (VLAN {link['vlan_id']})")
        print("="*70)
    
    def delete_slice_menu(self):
        slice_id = input("\nSlice ID: ").strip()
        success, msg = orchestrator.delete_slice(self.current_user, slice_id)
        print(f"\n{msg}")
    
    def create_link_menu(self):
        slice_id = input("\nSlice ID: ").strip()
        
        # Show available VMs and their interfaces
        slice_data = db.get_slice(slice_id)
        if not slice_data:
            print("\n❌ Slice not found")
            return
        
        print("\nAvailable VMs and interfaces:")
        for vm in slice_data.get("vms", []):
            print(f"  VM {vm['vm_id']}: {vm['name']}")
            for iface in vm.get("interfaces", []):
                if iface["name"] != "eth0":  # Skip management interface
                    link_status = f"(connected to Link {iface['link_id']})" if iface.get('link_id') else "(unconnected)"
                    print(f"    - {iface['name']} {link_status}")
        
        vm1_id = input("\nFirst VM ID: ").strip()
        vm1_interface = input("First VM interface (e.g., eth1): ").strip()
        vm2_id = input("Second VM ID: ").strip()
        vm2_interface = input("Second VM interface (e.g., eth1): ").strip()
        
        # Validate input
        try:
            vm1_id_int = int(vm1_id)
            vm2_id_int = int(vm2_id)
        except ValueError:
            print("\n❌ Error: VM IDs must be numbers (e.g., 1025, not 'vm1')")
            return
        
        success, result = orchestrator.create_link(
            self.current_user, slice_id, vm1_id_int, vm1_interface, vm2_id_int, vm2_interface
        )
        if success:
            print(f"\n✅ Link created! VLAN: {result['vlan_id']}")
        else:
            print(f"\n❌ Error: {result}")
    
    def deploy_slice_menu(self):
        slice_id = input("\nSlice ID to deploy: ").strip()
        success, msg = orchestrator.deploy_slice(self.current_user, slice_id)
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
