"""
Topology Generator - Create predefined network topologies
Supports: Ring, Bus, Linear, Star, Full Mesh
"""
import logging

logger = logging.getLogger(__name__)


class TopologyGenerator:
    """Generate predefined network topologies"""
    
    @staticmethod
    def generate_ring(num_vms, base_name="vm", flavor="cirros", internet=False):
        """
        Generate ring topology
        Each VM connects to next VM, last connects to first
        
        Args:
            num_vms: Number of VMs
            base_name: Base name for VMs (will append numbers)
            flavor: VM flavor
            internet: Enable internet on all VMs
            
        Returns:
            (vms_config, links_config)
        """
        if num_vms < 3:
            raise ValueError("Ring topology requires at least 3 VMs")
        
        vms = []
        links = []
        
        # Create VMs
        for i in range(num_vms):
            vms.append({
                'name': f"{base_name}{i+1}",
                'flavor': flavor,
                'internet_enabled': internet
            })
        
        # Create ring links (0->1, 1->2, ..., n-1->0)
        for i in range(num_vms):
            next_i = (i + 1) % num_vms
            links.append({
                'vm1_index': i,
                'vm2_index': next_i,
                'description': f"Link {i+1}"
            })
        
        return vms, links
    
    @staticmethod
    def generate_bus(num_vms, base_name="vm", flavor="cirros", internet=False):
        """
        Generate bus topology
        Linear chain: VM1 - VM2 - VM3 - ... - VMn
        
        Args:
            num_vms: Number of VMs
            base_name: Base name for VMs
            flavor: VM flavor
            internet: Enable internet
            
        Returns:
            (vms_config, links_config)
        """
        if num_vms < 2:
            raise ValueError("Bus topology requires at least 2 VMs")
        
        vms = []
        links = []
        
        # Create VMs
        for i in range(num_vms):
            vms.append({
                'name': f"{base_name}{i+1}",
                'flavor': flavor,
                'internet_enabled': internet
            })
        
        # Create linear links (0-1, 1-2, 2-3, ...)
        for i in range(num_vms - 1):
            links.append({
                'vm1_index': i,
                'vm2_index': i + 1,
                'description': f"Link {i+1}"
            })
        
        return vms, links
    
    @staticmethod
    def generate_star(num_vms, base_name="vm", flavor="cirros", internet=False, center_name="center"):
        """
        Generate star topology
        One central VM connected to all others
        
        Args:
            num_vms: Total number of VMs (including center)
            base_name: Base name for peripheral VMs
            flavor: VM flavor
            internet: Enable internet
            center_name: Name of center VM
            
        Returns:
            (vms_config, links_config)
        """
        if num_vms < 3:
            raise ValueError("Star topology requires at least 3 VMs")
        
        vms = []
        links = []
        
        # Create center VM
        vms.append({
            'name': center_name,
            'flavor': flavor,
            'internet_enabled': internet
        })
        
        # Create peripheral VMs
        for i in range(1, num_vms):
            vms.append({
                'name': f"{base_name}{i}",
                'flavor': flavor,
                'internet_enabled': internet
            })
        
        # Connect all to center (index 0)
        for i in range(1, num_vms):
            links.append({
                'vm1_index': 0,
                'vm2_index': i,
                'description': f"Link to {base_name}{i}"
            })
        
        return vms, links
    
    @staticmethod
    def generate_full_mesh(num_vms, base_name="vm", flavor="cirros", internet=False):
        """
        Generate full mesh topology
        Every VM connects to every other VM
        
        Args:
            num_vms: Number of VMs
            base_name: Base name for VMs
            flavor: VM flavor
            internet: Enable internet
            
        Returns:
            (vms_config, links_config)
        """
        if num_vms < 2:
            raise ValueError("Mesh topology requires at least 2 VMs")
        
        if num_vms > 6:
            logger.warning(f"Full mesh with {num_vms} VMs will create {num_vms*(num_vms-1)//2} links")
        
        vms = []
        links = []
        
        # Create VMs
        for i in range(num_vms):
            vms.append({
                'name': f"{base_name}{i+1}",
                'flavor': flavor,
                'internet_enabled': internet
            })
        
        # Create all possible links
        for i in range(num_vms):
            for j in range(i + 1, num_vms):
                links.append({
                    'vm1_index': i,
                    'vm2_index': j,
                    'description': f"Link {i+1}-{j+1}"
                })
        
        return vms, links
    
    @staticmethod
    def get_topology_info(topology_type):
        """Get information about a topology type"""
        info = {
            'ring': {
                'name': 'Ring',
                'description': 'Each VM connects to the next, forming a circle',
                'min_vms': 3,
                'links_formula': 'n',
                'icon': '⭕'
            },
            'bus': {
                'name': 'Bus/Linear',
                'description': 'VMs connected in a line',
                'min_vms': 2,
                'links_formula': 'n-1',
                'icon': '➖'
            },
            'star': {
                'name': 'Star',
                'description': 'One central VM connected to all others',
                'min_vms': 3,
                'links_formula': 'n-1',
                'icon': '⭐'
            },
            'mesh': {
                'name': 'Full Mesh',
                'description': 'Every VM connects to every other VM',
                'min_vms': 2,
                'links_formula': 'n*(n-1)/2',
                'icon': '🕸️'
            }
        }
        return info.get(topology_type, {})
