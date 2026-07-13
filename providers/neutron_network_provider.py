"""
Neutron Network Provider - OpenStack networking implementation
Uses OpenStack SDK for network/subnet/port management via API calls
"""
import logging
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed
from providers.base_compute import BaseNetworkProvider

logger = logging.getLogger(__name__)


class NeutronNetworkProvider(BaseNetworkProvider):
    """
    Network provider for OpenStack cluster using Neutron API
    
    Key features:
    - Creates Neutron networks/subnets/ports via API
    - Parallel network creation with ThreadPoolExecutor
    - Automatic subnet allocation from pool
    - Internet network with gateway 10.60.8.126
    """
    
    # Default subnet pool for inter-VM links
    DEFAULT_ADDRESS_POOL = "10.200.0.0/16"
    DEFAULT_PREFIX_LENGTH = 29  # /29 = 8 IPs per network
    
    # Internet/management network (pre-existing in OpenStack)
    INTERNET_NETWORK_NAME = "external"  # External provider network
    INTERNET_GATEWAY = "10.60.8.126"  # Physical switch gateway
    
    def __init__(self, connection):
        """
        Initialize Neutron network provider
        
        Args:
            connection: OpenStack SDK connection
        """
        self.connection = connection
    
    def create_network(self, vlan_id, cidr, gateway_ip, dhcp_enabled=True, create_gateway=True):
        """
        Create a Neutron network with subnet
        
        Args:
            vlan_id: VLAN ID (used for network name)
            cidr: CIDR for subnet (e.g., "192.168.100.0/29")
            gateway_ip: Gateway IP address
            dhcp_enabled: Enable DHCP on subnet
            create_gateway: Create gateway (always True for Neutron)
        
        Returns:
            bool: True if successful
        """
        try:
            network_name = f"slice-vlan-{vlan_id}"
            subnet_name = f"{network_name}-subnet"
            
            logger.info(f"Creating Neutron network {network_name} with CIDR {cidr}")
            
            # Create network
            network = self.connection.network.create_network(
                name=network_name,
                admin_state_up=True,
            )
            
            # Create subnet
            subnet = self.connection.network.create_subnet(
                name=subnet_name,
                network_id=network.id,
                ip_version=4,
                cidr=cidr,
                gateway_ip=gateway_ip,
                enable_dhcp=dhcp_enabled,
            )
            
            logger.info(f"Created network {network.id} and subnet {subnet.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create network for VLAN {vlan_id}: {e}")
            return False
    
    def create_networks_parallel(self, network_specs):
        """
        Create multiple networks in parallel for optimal deployment speed
        
        This is part of the "optimized deployment by design" pattern:
        - Phase 1: Create all networks/subnets concurrently
        - Phase 2: Create VMs (which need networks to exist first)
        
        Args:
            network_specs: List of dicts with keys:
                - vlan_id: VLAN ID
                - cidr: CIDR notation
                - gateway_ip: Gateway IP
                - dhcp_enabled: Enable DHCP
        
        Returns:
            dict: {vlan_id: (success, network_id, subnet_id), ...}
        """
        results = {}
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_vlan = {
                executor.submit(
                    self._create_network_with_details,
                    spec
                ): spec["vlan_id"]
                for spec in network_specs
            }
            
            for future in as_completed(future_to_vlan):
                vlan_id = future_to_vlan[future]
                try:
                    success, network_id, subnet_id = future.result()
                    results[vlan_id] = (success, network_id, subnet_id)
                    if success:
                        logger.info(f"Network for VLAN {vlan_id} deployed: {network_id}")
                    else:
                        logger.error(f"Network for VLAN {vlan_id} deployment failed")
                except Exception as e:
                    logger.error(f"Network for VLAN {vlan_id} exception: {e}")
                    results[vlan_id] = (False, None, None)
        
        return results
    
    def _create_network_with_details(self, spec):
        """
        Create network and return detailed info (for parallel execution)
        
        Args:
            spec: Network specification dict
        
        Returns:
            tuple: (success, network_id, subnet_id)
        """
        try:
            vlan_id = spec["vlan_id"]
            cidr = spec["cidr"]
            gateway_ip = spec["gateway_ip"]
            dhcp_enabled = spec.get("dhcp_enabled", True)
            
            network_name = f"slice-vlan-{vlan_id}"
            subnet_name = f"{network_name}-subnet"
            
            # Create network
            network = self.connection.network.create_network(
                name=network_name,
                admin_state_up=True,
            )
            
            # Create subnet
            subnet = self.connection.network.create_subnet(
                name=subnet_name,
                network_id=network.id,
                ip_version=4,
                cidr=cidr,
                gateway_ip=gateway_ip,
                enable_dhcp=dhcp_enabled,
            )
            
            return True, network.id, subnet.id
            
        except Exception as e:
            logger.error(f"Failed to create network {spec.get('vlan_id')}: {e}")
            return False, None, None
    
    def delete_network(self, vlan_id):
        """
        Delete a Neutron network and its subnet
        
        Args:
            vlan_id: VLAN ID (used to find network by name)
        
        Returns:
            bool: True if successful
        """
        try:
            network_name = f"slice-vlan-{vlan_id}"
            
            # Find network by name
            networks = list(self.connection.network.networks(name=network_name))
            if not networks:
                logger.warning(f"Network {network_name} not found for deletion")
                return True  # Already deleted
            
            network = networks[0]
            
            # Delete all ports in this network first
            ports = list(self.connection.network.ports(network_id=network.id))
            for port in ports:
                try:
                    self.connection.network.delete_port(port.id, ignore_missing=True)
                except Exception as e:
                    logger.warning(f"Failed to delete port {port.id}: {e}")
            
            # Delete all subnets
            subnets = list(self.connection.network.subnets(network_id=network.id))
            for subnet in subnets:
                try:
                    self.connection.network.delete_subnet(subnet.id, ignore_missing=True)
                except Exception as e:
                    logger.warning(f"Failed to delete subnet {subnet.id}: {e}")
            
            # Delete network
            self.connection.network.delete_network(network.id, ignore_missing=True)
            
            logger.info(f"Deleted network {network_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete network for VLAN {vlan_id}: {e}")
            return False
    
    def create_interface(self, vm_id, interface_name, vlan_id):
        """
        Not needed for OpenStack - ports are created before VM launch
        
        In OpenStack workflow:
        1. Create network/subnet
        2. Create ports on network
        3. Launch VM with ports
        
        This is different from BareMetalProvider which creates TAP interfaces
        """
        return True
    
    def create_port(self, network_id, subnet_id, port_name):
        """
        Create a Neutron port on a network
        
        Args:
            network_id: Network ID
            subnet_id: Subnet ID
            port_name: Port name
        
        Returns:
            dict: Port information with keys: id, ip_address, mac_address
        """
        try:
            port = self.connection.network.create_port(
                name=port_name,
                network_id=network_id,
                admin_state_up=True,
                fixed_ips=[
                    {"subnet_id": subnet_id}
                ],
            )
            
            # Extract IP and MAC
            ip_address = None
            if hasattr(port, "fixed_ips") and port.fixed_ips:
                ip_address = port.fixed_ips[0].get("ip_address")
            
            mac_address = getattr(port, "mac_address", None)
            
            return {
                "id": port.id,
                "ip_address": ip_address,
                "mac_address": mac_address,
            }
            
        except Exception as e:
            logger.error(f"Failed to create port {port_name}: {e}")
            return None
    
    def create_internet_port(self, vm_name, slice_name):
        """
        Create a port on the internet/management network
        
        The internet network is pre-existing in OpenStack with:
        - Network name: "external" (external provider network)
        - Gateway: 10.60.8.126
        - VLAN: 10 (configured at physical switch level)
        
        Args:
            vm_name: VM name
            slice_name: Slice name
        
        Returns:
            dict: Port information or None
        """
        try:
            # Find the provider/internet network
            networks = list(self.connection.network.networks(name=self.INTERNET_NETWORK_NAME))
            if not networks:
                logger.error(f"Internet network '{self.INTERNET_NETWORK_NAME}' not found")
                return None
            
            internet_network = networks[0]
            
            # Get subnet
            subnets = list(self.connection.network.subnets(network_id=internet_network.id))
            if not subnets:
                logger.error(f"No subnet found for internet network")
                return None
            
            internet_subnet = subnets[0]
            
            port_name = f"{slice_name}-{vm_name}-internet"
            
            logger.info(f"Creating internet port {port_name} on network {internet_network.id}")
            
            port = self.connection.network.create_port(
                name=port_name,
                network_id=internet_network.id,
                admin_state_up=True,
                fixed_ips=[
                    {"subnet_id": internet_subnet.id}
                ],
            )
            
            # Extract IP and MAC
            ip_address = None
            if hasattr(port, "fixed_ips") and port.fixed_ips:
                ip_address = port.fixed_ips[0].get("ip_address")
            
            mac_address = getattr(port, "mac_address", None)
            
            logger.info(f"Created internet port {port.id} with IP {ip_address}")
            
            return {
                "id": port.id,
                "ip_address": ip_address,
                "mac_address": mac_address,
            }
            
        except Exception as e:
            logger.error(f"Failed to create internet port for VM {vm_name}: {e}")
            return None
    
    def get_internet_network_id(self):
        """
        Get the ID of the internet/external network
        
        Returns:
            str: Network ID or None if not found
        """
        try:
            networks = list(self.connection.network.networks(name=self.INTERNET_NETWORK_NAME))
            if not networks:
                logger.error(f"Internet network '{self.INTERNET_NETWORK_NAME}' not found")
                return None
            
            return networks[0].id
            
        except Exception as e:
            logger.error(f"Failed to get internet network ID: {e}")
            return None
    
    def allocate_subnets(self, count, address_pool=None, prefix_length=None):
        """
        Allocate available subnets from the pool
        
        This checks existing Neutron subnets to avoid overlaps
        
        Args:
            count: Number of subnets needed
            address_pool: CIDR pool (default: 10.200.0.0/16)
            prefix_length: Subnet prefix length (default: 29)
        
        Returns:
            list: List of ipaddress.IPv4Network objects
        """
        if address_pool is None:
            address_pool = self.DEFAULT_ADDRESS_POOL
        if prefix_length is None:
            prefix_length = self.DEFAULT_PREFIX_LENGTH
        
        try:
            # Parse pool
            pool_network = ipaddress.ip_network(address_pool, strict=False)
            
            # Get existing subnets from Neutron
            existing_networks = []
            for subnet in self.connection.network.subnets():
                cidr = getattr(subnet, "cidr", None)
                if cidr:
                    try:
                        existing_networks.append(ipaddress.ip_network(cidr, strict=False))
                    except ValueError:
                        pass
            
            # Find available subnets
            selected_networks = []
            for candidate in pool_network.subnets(new_prefix=prefix_length):
                # Check if this subnet overlaps with any existing subnet
                overlaps = any(
                    candidate.overlaps(existing)
                    for existing in existing_networks
                )
                
                if not overlaps:
                    selected_networks.append(candidate)
                    existing_networks.append(candidate)  # Mark as used
                    
                    if len(selected_networks) == count:
                        return selected_networks
            
            raise Exception(f"Not enough available subnets in pool {address_pool}")
            
        except Exception as e:
            logger.error(f"Failed to allocate subnets: {e}")
            return []
