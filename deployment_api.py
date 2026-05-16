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
    
    def create_vm_with_qcow(self, slice_id, vm_id, vm_name, owner, worker_ip, vlan_ids, base_image_path=None):
        try:
            self.vnc_port_counter += 1
            vnc_port = self.vnc_port_counter
            macs = self.generate_unique_macs(vm_id, count=min(3, len(vlan_ids)+1))
            mgmt_ip = f"10.60.7.{100 + vm_id % 100}"
            
            interfaces = [
                Interface("eth0", vlan_id=None, mac=macs[0], ip_config={"ip": mgmt_ip, "cidr": "10.60.7.0/24"})
            ]
            for idx, vlan_id in enumerate(vlan_ids[:2]):
                interfaces.append(Interface(f"eth{idx+1}", vlan_id=vlan_id, mac=macs[idx+1] if idx+1 < len(macs) else f"{self.mac_base}:{vm_id%256:02x}:{idx+1:02x}"))
            
            image_path = base_image_path or self.base_image_path
            success, qcow_img = self.qcow_mgr.create_backing_image(worker_ip, vm_name, image_path, vlan_ids) if image_path else (True, None)
            
            if not success:
                return False, None
            
            vm = VM(vm_id, vm_name, owner, worker_ip, vnc_port, interfaces, qcow_image=qcow_img)
            vm.status = "running"
            logger.info(f"VM {vm_name} created (VNC: {vnc_port}, QCOW: {qcow_img})")
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
