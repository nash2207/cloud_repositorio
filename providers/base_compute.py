"""
Base Compute Provider - Abstract interface for VM lifecycle
"""
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class BaseComputeProvider(ABC):
    """Abstract base class for compute providers (Bare-Metal, OpenStack, etc.)"""
    
    @abstractmethod
    def launch_vm(self, worker_ip, vm_dict):
        """
        Launch a VM instance
        
        Args:
            worker_ip: Target worker/node IP
            vm_dict: VM configuration dictionary
            
        Returns:
            (success: bool, pid/instance_id: str)
        """
        pass
    
    @abstractmethod
    def stop_vm(self, worker_ip, vm_dict):
        """
        Stop a VM instance
        
        Args:
            worker_ip: Target worker/node IP
            vm_dict: VM configuration dictionary
            
        Returns:
            success: bool
        """
        pass
    
    @abstractmethod
    def get_running_vms(self, worker_ip):
        """
        Get list of running VMs on a worker
        
        Args:
            worker_ip: Worker IP to query
            
        Returns:
            List of VM info dicts
        """
        pass


class BaseNetworkProvider(ABC):
    """Abstract base class for network providers (OVS, Neutron, etc.)"""
    
    @abstractmethod
    def create_network(self, vlan_id, cidr, gateway_ip, dhcp_enabled=True):
        """
        Create a network/VLAN
        
        Args:
            vlan_id: VLAN ID
            cidr: Network CIDR (e.g., "192.168.1.0/24")
            gateway_ip: Gateway IP address
            dhcp_enabled: Enable DHCP server
            
        Returns:
            success: bool
        """
        pass
    
    @abstractmethod
    def delete_network(self, vlan_id):
        """
        Delete a network/VLAN
        
        Args:
            vlan_id: VLAN ID to delete
            
        Returns:
            success: bool
        """
        pass
    
    @abstractmethod
    def create_interface(self, vm_id, interface_name, vlan_id):
        """
        Create/attach a network interface to VM
        
        Args:
            vm_id: VM identifier
            interface_name: Interface name (eth0, ens3, etc.)
            vlan_id: VLAN to attach to
            
        Returns:
            success: bool
        """
        pass
