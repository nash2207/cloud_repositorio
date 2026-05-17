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
            print("4. View my Slices")
            print("5. Delete Slice")
            print("6. Logout")
            choice = input("\nChoice: ").strip()
            if choice == "1":
                self.view_quota()
            elif choice == "2":
                self.create_slice_menu()
            elif choice == "3":
                self.add_vm_menu()
            elif choice == "4":
                self.view_slices()
            elif choice == "5":
                self.delete_slice_menu()
            elif choice == "6":
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
        
        print("\nAvailable images:")
        print("1. cirros-0.6.2-x86_64-disk.img (Lightweight)")
        print("2. focal-server-cloudimg-amd64.img (Ubuntu 20.04)")
        image_choice = input("Choose image (1-2): ").strip()
        
        images = {
            "1": "/tmp/vm_images/cirros-0.6.2-x86_64-disk.img",
            "2": "/tmp/vm_images/focal-server-cloudimg-amd64.img"
        }
        base_image = images.get(image_choice, images["1"])
        
        internet = input("Enable internet access? (y/n): ").strip().lower() == 'y'
        
        success, result = orchestrator.add_vm_to_slice(
            self.current_user, slice_id, vm_name, 
            base_image_path=base_image, 
            internet_enabled=internet
        )
        if success:
            print(f"\n✅ VM added! ID: {result['vm_id']}, VNC: {result['vnc_port']}")
        else:
            print(f"\n❌ Error: {result}")
    
    def view_slices(self):
        user = db.get_user(self.current_user)
        slice_ids = user.get('slices', [])
        if not slice_ids:
            print("\nNo Slices found.")
            return
        print("\n" + "="*50)
        for slice_id in slice_ids:
            slice_data = db.get_slice(slice_id)
            if slice_data:
                vm_count = len(slice_data.get("vms", []))
                vlan_ids = slice_data.get("vlan_ids", [])
                print(f"Slice {slice_id}: {vm_count} VMs, VLANs: {vlan_ids}")
                for vm in slice_data.get("vms", []):
                    print(f"  └─ VM {vm['vm_id']}: {vm['name']} (VNC: {vm['vnc_port']}, Worker: {vm['worker_ip']})")
    
    def delete_slice_menu(self):
        slice_id = input("\nSlice ID: ").strip()
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
