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
            print("2. Create VM")
            print("3. View my VMs")
            print("4. Delete VM")
            print("5. Logout")
            choice = input("\nChoice: ").strip()
            if choice == "1":
                self.view_quota()
            elif choice == "2":
                self.create_vm_menu()
            elif choice == "3":
                self.view_vms()
            elif choice == "4":
                self.delete_vm_menu()
            elif choice == "5":
                self.current_user = None
                break
    
    def view_quota(self):
        user = db.get_user(self.current_user)
        if user:
            print(f"\nQuota: {user.get('used_vms', 0)}/{user.get('quota_vms', 10)} VMs used")
    
    def create_vm_menu(self):
        vm_name = input("\nVM name: ").strip()
        vlan_ids = [db.get_next_vlan_id(), db.get_next_vlan_id()]
        
        success, result = orchestrator.create_vm(self.current_user, vm_name, vlan_ids)
        if success:
            self.current_slice["id"] = result.get('vm_id')
            self.current_slice["user"] = self.current_user
            self.current_slice["orchestrator"] = orchestrator
            print(f"\n✅ VM created! ID: {result['vm_id']}, VNC: {result['vnc_port']}")
        else:
            print(f"\n❌ Error: {result}")
    
    def view_vms(self):
        user = db.get_user(self.current_user)
        vms = user.get('slices', [])
        if not vms:
            print("\nNo VMs found.")
            return
        for vm_id in vms:
            print(f"  VM {vm_id}")
    
    def delete_vm_menu(self):
        vm_id = input("\nVM ID: ").strip()
        success, msg = orchestrator.delete_vm(self.current_user, vm_id)
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
