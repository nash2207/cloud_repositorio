"""Deployment API for creating/deleting VMs with QCOW2"""
import random, logging, os
from models import VM, Interface, Network
from remote_executor import RemoteExecutor
from qcow_manager import QCOWManager
logger = logging.getLogger(__name__)

class DeploymentAPI:
    def __init__(self, remote_executor, base_image_path=None):
        self.executor = remote_executor
        self.qcow_mgr = QCOWManager(remote_executor)
        self.base_image_path = base_image_path
        self.vnc_port_counter = 5900
        self.mac_base = "52:54:00:20:19:32"
    
    def generate_unique_macs(self, vm_id, count=3):
        macs = []
        for i in range(count):
            mac = f"{self.mac_base}:{vm_id%256:02x}:{i:02x}"
            macs.append(mac)
        return macs
    
    def create_vm_with_qcow(self, slice_id, vm_id, vm_name, owner, worker_ip, flavor, data_interfaces_count, internet_enabled=False):
        try:
            self.vnc_port_counter += 1
            vnc_port = self.vnc_port_counter
            
            flavor_spec = flavor
            interface_count = data_interfaces_count + 1  # +1 for eth0
            
            macs = self.generate_unique_macs(vm_id, count=interface_count)
            mgmt_ip = f"10.60.7.{100 + vm_id % 100}"
            
            interfaces = []
            
            # eth0 always for management (VLAN 400 if internet enabled)
            if internet_enabled:
                interfaces.append(Interface("eth0", vlan_id=400, mac=macs[0], 
                                          ip_config={"ip": mgmt_ip, "cidr": "10.60.7.0/24", "gateway": "10.60.7.1"}))
            else:
                interfaces.append(Interface("eth0", vlan_id=None, mac=macs[0], ip_config=None))
            
            # Data interfaces (eth1, eth2, ...) - unconnected initially
            for i in range(1, data_interfaces_count + 1):
                interfaces.append(Interface(f"eth{i}", vlan_id=None, mac=macs[i], link_id=None))
            
            image_path = flavor_spec.get("image")
            success, qcow_img = self.qcow_mgr.create_backing_image(worker_ip, vm_name, image_path, []) if image_path else (True, None)
            
            if not success:
                return False, None
            
            vm = VM(vm_id, vm_name, owner, worker_ip, vnc_port, interfaces, flavor=flavor_spec, qcow_image=qcow_img)
            vm.status = "design"
            logger.info(f"VM {vm_name} created (VNC: {vnc_port}, Flavor: {flavor_spec}, Internet: {internet_enabled}, Data IFs: {data_interfaces_count})")
            return True, vm
        except Exception as e:
            logger.error(f"VM creation error: {e}")
            return False, None
    
    def delete_vm(self, vm):
        try:
            if vm.qcow_image:
                self.qcow_mgr.delete_image(vm.worker_ip, vm.qcow_image)
            vm.status = "deleted"
            logger.info(f"VM {vm.name} deleted")
            return True
        except Exception as e:
            logger.error(f"Delete error: {e}")
            return False
    
    def delete_vm_dict(self, vm_dict):
        try:
            if vm_dict.get("qcow_image"):
                self.qcow_mgr.delete_image(vm_dict.get("worker_ip"), vm_dict.get("qcow_image"))
            logger.info(f"VM {vm_dict.get('name')} deleted")
            return True
        except Exception as e:
            logger.error(f"Delete error: {e}")
            return False
