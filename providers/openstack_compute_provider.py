"""
OpenStack Compute Provider - Nova implementation
Uses OpenStack SDK for VM management via API calls to headnode (10.60.8.1)
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from providers.base_compute import BaseComputeProvider

logger = logging.getLogger(__name__)


class OpenStackComputeProvider(BaseComputeProvider):
    """
    Compute provider for OpenStack cluster using Nova API
    
    Key differences from BareMetalProvider:
    - Uses OpenStack SDK instead of SSH/libvirt
    - No monitoring/genetic algorithm (uses Nova scheduler)
    - Parallel VM deployment with ThreadPoolExecutor
    - API calls to headnode at 10.60.8.1
    """
    
    def __init__(self, connection):
        """
        Initialize OpenStack compute provider
        
        Args:
            connection: OpenStack SDK connection (from openstacksdk)
        """
        self.connection = connection
        self.executor = None  # No SSH executor needed for OpenStack
    
    def launch_vm(self, worker_ip, vm_dict):
        """
        Launch a VM using Nova API
        
        Args:
            worker_ip: Ignored for OpenStack (Nova scheduler decides)
            vm_dict: VM configuration dict containing:
                - name: VM name
                - image_id: OpenStack image ID (from Glance)
                - flavor_id: OpenStack flavor ID
                - openstack_networks: List of network dicts with network_id
        
        Returns:
            tuple: (success: bool, server_id or None)
        """
        try:
            vm_name = vm_dict.get("name")
            image_id = vm_dict.get("image_id")
            flavor_id = vm_dict.get("flavor_id")
            openstack_networks = vm_dict.get("openstack_networks", [])
            
            # Build networks list for Nova (using network IDs, not ports)
            # Nova will auto-create ports and bind them to the assigned host
            networks = []
            for net_info in openstack_networks:
                network_id = net_info.get("network_id")
                if network_id:
                    networks.append({"uuid": network_id})
            
            if not networks:
                logger.error(f"VM {vm_name} has no networks configured")
                return False, None
            
            # Create server using Nova API
            logger.info(f"Creating VM {vm_name} with image {image_id}, flavor {flavor_id}, {len(networks)} network(s)")
            
            server = self.connection.compute.create_server(
                name=vm_name,
                image_id=image_id,
                flavor_id=flavor_id,
                networks=networks,
            )
            
            logger.info(f"VM {vm_name} created with ID {server.id}, waiting for ACTIVE state...")
            
            # Wait for server to become ACTIVE
            server = self.connection.compute.wait_for_server(
                server,
                status="ACTIVE",
                failures=["ERROR"],
                interval=2,
                wait=120,  # 2 minute timeout (reduced for faster debugging)
            )
            
            logger.info(f"VM {vm_name} is now ACTIVE (ID: {server.id})")
            return True, server.id
            
        except Exception as e:
            logger.error(f"Failed to launch VM {vm_dict.get('name')}: {e}")
            return False, None
    
    def launch_vms_parallel(self, vm_assignments):
        """
        Launch multiple VMs in parallel using ThreadPoolExecutor
        
        This implements the "optimized deployment by design" pattern:
        - All VMs launch concurrently
        - Error isolation: one VM failure doesn't stop others
        - Significant speed improvement (< 1 minute vs 3-4 minutes)
        
        Args:
            vm_assignments: List of (worker_ip, vm_dict) tuples
        
        Returns:
            dict: {vm_id: (success, server_id), ...}
        """
        results = {}
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_vm = {
                executor.submit(self.launch_vm, worker_ip, vm_dict): vm_dict.get("vm_id")
                for worker_ip, vm_dict in vm_assignments
            }
            
            for future in as_completed(future_to_vm):
                vm_id = future_to_vm[future]
                try:
                    success, server_id = future.result()
                    results[vm_id] = (success, server_id)
                    if success:
                        logger.info(f"VM {vm_id} deployed successfully: {server_id}")
                    else:
                        logger.error(f"VM {vm_id} deployment failed")
                except Exception as e:
                    logger.error(f"VM {vm_id} deployment exception: {e}")
                    results[vm_id] = (False, None)
        
        return results
    
    def stop_vm(self, worker_ip, vm_dict):
        """
        Stop a VM using Nova API
        
        Args:
            worker_ip: Ignored for OpenStack
            vm_dict: VM dict containing 'server_id'
        
        Returns:
            bool: True if stopped successfully
        """
        try:
            server_id = vm_dict.get("server_id") or vm_dict.get("openstack_server_id")
            if not server_id:
                logger.warning(f"No server_id found for VM {vm_dict.get('name')}")
                return False
            
            logger.info(f"Stopping VM {vm_dict.get('name')} (server {server_id})")
            
            # Delete server using Nova API
            self.connection.compute.delete_server(
                server_id,
                ignore_missing=True
            )
            
            # Wait for server to be deleted
            self._wait_server_deleted(server_id, timeout=120)
            
            logger.info(f"VM {vm_dict.get('name')} stopped")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop VM {vm_dict.get('name')}: {e}")
            return False
    
    def _wait_server_deleted(self, server_id, timeout=120):
        """
        Wait for server to be fully deleted
        
        Args:
            server_id: OpenStack server ID
            timeout: Maximum wait time in seconds
        """
        start_time = time.time()
        
        while time.time() - start_time <= timeout:
            try:
                server = self.connection.compute.get_server(server_id)
                if server is None:
                    return True
                time.sleep(2)
            except Exception:
                # Server not found - consider it deleted
                return True
        
        logger.warning(f"Server {server_id} deletion timeout after {timeout}s")
        return False
    
    def get_vm_info(self, worker_ip, vm_dict):
        """
        Get VM information from Nova
        
        Args:
            worker_ip: Ignored for OpenStack
            vm_dict: VM dict containing 'server_id'
        
        Returns:
            dict: VM information or None
        """
        try:
            server_id = vm_dict.get("server_id") or vm_dict.get("openstack_server_id")
            if not server_id:
                return None
            
            server = self.connection.compute.get_server(server_id)
            if not server:
                return None
            
            return {
                "id": server.id,
                "name": server.name,
                "status": server.status,
                "power_state": getattr(server, "power_state", None),
                "host": self._get_server_host(server),
            }
            
        except Exception as e:
            logger.error(f"Failed to get VM info: {e}")
            return None
    
    def _get_server_host(self, server):
        """
        Extract hypervisor host from server object
        
        Args:
            server: Nova server object
        
        Returns:
            str: Hypervisor hostname or None
        """
        possible_keys = (
            "OS-EXT-SRV-ATTR:host",
            "hypervisor_hostname",
            "host",
        )
        
        for key in possible_keys:
            value = getattr(server, key, None)
            if value:
                return str(value)
        
        # Try from to_dict()
        try:
            data = server.to_dict()
            for key in possible_keys:
                if key in data and data[key]:
                    return str(data[key])
        except Exception:
            pass
        
        return None
    
    def get_running_vms(self, worker_ip):
        """
        Get list of running VMs on a worker (OpenStack compute node)
        
        For OpenStack, this queries Nova for all servers and filters by
        the hypervisor host.
        
        Args:
            worker_ip: Worker/compute node IP (used to match hypervisor hostname)
        
        Returns:
            list: List of VM info dicts
        """
        try:
            # Query all servers from Nova
            servers = self.connection.compute.servers(details=True)
            
            running_vms = []
            for server in servers:
                # Filter by hypervisor host if worker_ip matches
                host = self._get_server_host(server)
                
                # If worker_ip is provided, only include VMs on that host
                # Otherwise, return all VMs (for cluster-wide queries)
                if worker_ip and host and worker_ip not in host:
                    continue
                
                # Only include ACTIVE servers
                if server.status == "ACTIVE":
                    running_vms.append({
                        "id": server.id,
                        "name": server.name,
                        "status": server.status,
                        "host": host,
                    })
            
            logger.debug(f"Found {len(running_vms)} running VMs" + (f" on {worker_ip}" if worker_ip else ""))
            return running_vms
            
        except Exception as e:
            logger.error(f"Failed to get running VMs: {e}")
            return []
