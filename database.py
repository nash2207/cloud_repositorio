"""Database layer with YAML persistence"""
import yaml, threading, time
from models import User, Slice
class Database:
    def __init__(self, filepath="database.yaml"):
        self.filepath = filepath
        self.data = {"users": {}, "slices": {}, "next_vm_id": 1000, "next_vlan_id": 100}
        self.lock = threading.RLock()
        self.load()
    def load(self):
        try:
            with open(self.filepath, 'r') as f:
                self.data = yaml.safe_load(f) or self.data
        except FileNotFoundError:
            self.save()
    def save(self):
        with self.lock:
            with open(self.filepath, 'w') as f:
                yaml.dump(self.data, f, default_flow_style=False)
    def get_user(self, username):
        return self.data["users"].get(username)
    def add_user(self, user_dict):
        with self.lock:
            self.data["users"][user_dict["username"]] = user_dict
            self.save()
    def update_user(self, username, user_dict):
        with self.lock:
            self.data["users"][username] = user_dict
            self.save()
    def get_slice(self, slice_id):
        return self.data["slices"].get(str(slice_id))
    def add_slice(self, slice_dict):
        with self.lock:
            self.data["slices"][str(slice_dict["slice_id"])] = slice_dict
            self.save()
    def update_slice(self, slice_id, slice_dict):
        with self.lock:
            self.data["slices"][str(slice_id)] = slice_dict
            self.save()
    def delete_slice(self, slice_id):
        with self.lock:
            if str(slice_id) in self.data["slices"]:
                del self.data["slices"][str(slice_id)]
                self.save()
    def get_next_vm_id(self):
        with self.lock:
            vm_id = self.data["next_vm_id"]
            self.data["next_vm_id"] += 1
            self.save()
            return vm_id
    def get_next_vlan_id(self):
        with self.lock:
            vlan_id = self.data["next_vlan_id"]
            self.data["next_vlan_id"] += 1
            self.save()
            return vlan_id
    def get_all_slices_for_user(self, username):
        return [s for s in self.data["slices"].values() if s["owner"] == username]
