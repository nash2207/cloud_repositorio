"""Deployment API for creating/deleting VMs with QCOW2"""
import logging
from models import VM, Interface, Flavor
from qcow_manager import QCOWManager

logger = logging.getLogger(__name__)


class DeploymentAPI:
    """API for VM deployment - flavor-aware interface naming"""
    
    def __init__(self, remote_executor):
        self.executor = remote_executor
        self.qcow_mgr = QCOWManager(remote_executor)
        self.vnc_port_counter = 5900
    
    def generate_unique_macs(self, vm_id, count):
        """Generate unique MAC addresses for VM interfaces"""
        macs = []
        for i in range(count):
            # Generate 6-byte MAC address (QEMU format)
            mac = f"52:54:00:{(vm_id >> 8) & 0xFF:02x}:{vm_id & 0xFF:02x}:{i:02x}"
            macs.append(mac)
        return macs
    
    def create_vm_with_qcow(self, slice_id, vm_id, vm_name, owner, worker_ip, 
                            flavor_name, internet_enabled=False):
        """
        Create VM with only management interface initially
        Data interfaces are added dynamically when creating links
        
        Args:
            slice_id: Slice ID
            vm_id: Unique VM ID
            vm_name: VM name
            owner: Owner username
            worker_ip: Worker node IP
            flavor_name: Flavor name (cirros, ubuntu)
            internet_enabled: Enable internet access (VLAN 400)
        
        Returns:
            (success: bool, vm: VM object)
        """
        try:
            self.vnc_port_counter += 1
            vnc_port = self.vnc_port_counter
            
            flavor_spec = Flavor.get(flavor_name)
            if not flavor_spec:
                logger.error(f"Invalid flavor: {flavor_name}")
                return False, None
            
            # Generate MAC for management interface only
            macs = self.generate_unique_macs(vm_id, count=1)
            mgmt_ip = f"10.60.7.{100 + vm_id % 100}"
            
            interfaces = []
            
            # Only management interface (eth0 or ens3)
            mgmt_iface_name = Flavor.get_interface_name(flavor_name, 0)
            if internet_enabled:
                interfaces.append(Interface(
                    mgmt_iface_name, 
                    vlan_id=400, 
                    mac=macs[0],
                    ip_config={"ip": mgmt_ip, "cidr": "10.60.7.0/24", "gateway": "10.60.7.1"}
                ))
            else:
                interfaces.append(Interface(mgmt_iface_name, vlan_id=None, mac=macs[0], ip_config=None))
            
            # Create QCOW2 backing image
            image_path = flavor_spec.get("image")
            # Don't create QCOW2 yet if worker is not assigned - defer until deployment
            if worker_ip != "PENDING" and image_path:
                success, qcow_img = self.qcow_mgr.create_backing_image(
                    worker_ip, vm_name, image_path, []
                )
                if not success:
                    logger.error(f"Failed to create QCOW2 image for {vm_name}")
                    return False, None
            else:
                # Defer QCOW2 creation until deployment when worker_ip is assigned
                qcow_img = None
                logger.info(f"QCOW2 creation deferred for {vm_name} until deployment")
            
            # Create VM object
            vm = VM(
                vm_id, vm_name, owner, worker_ip, vnc_port, interfaces, 
                flavor=flavor_name, qcow_image=qcow_img
            )
            vm.status = "design"
            
            logger.info(
                f"VM {vm_name} created: Flavor={flavor_name}, "
                f"Management={mgmt_iface_name}, Internet={internet_enabled}, VNC={vnc_port}"
            )
            return True, vm
            
        except Exception as e:
            logger.error(f"VM creation error: {e}")
            return False, None
    
    def delete_vm_dict(self, vm_dict):
        """Delete VM and cleanup QCOW2 image"""
        try:
            if vm_dict.get("qcow_image"):
                self.qcow_mgr.delete_image(
                    vm_dict.get("worker_ip"), 
                    vm_dict.get("qcow_image")
                )
            logger.info(f"VM {vm_dict.get('name')} deleted")
            return True
        except Exception as e:
            logger.error(f"Delete error: {e}")
            return False
