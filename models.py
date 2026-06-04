"""OOP Models for Slice Manager with Graph-based Topology"""
class User:
    def __init__(self, username, password_hash, quota_vms=10):
        self.username = username
        self.password_hash = password_hash
        self.quota_vms = quota_vms
        self.used_vms = 0
        self.slices = []
    def can_create_vms(self, count):
        return (self.used_vms + count) <= self.quota_vms
    def to_dict(self):
        return {"username": self.username, "password_hash": self.password_hash, "quota_vms": self.quota_vms, "used_vms": self.used_vms, "slices": self.slices}

class Flavor:
    FLAVORS = {
        "cirros": {
            "cores": 1, 
            "ram_gb": 0.5, 
            "disk_gb": 1, 
            "image": "/tmp/vm_images/cirros-0.6.2-x86_64-disk.img",
            "interface_prefix": "eth"  # eth0, eth1, eth2...
        },
        "ubuntu": {
            "cores": 1, 
            "ram_gb": 0.5, 
            "disk_gb": 2.2, 
            "image": "/tmp/vm_images/focal-server-cloudimg-amd64.img",
            "interface_prefix": "ens"  # ens3, ens4, ens5...
        }
    }
    
    @staticmethod
    def get(flavor_name):
        return Flavor.FLAVORS.get(flavor_name)
    
    @staticmethod
    def get_interface_name(flavor_name, index):
        """Get interface name based on flavor and index"""
        flavor = Flavor.get(flavor_name)
        if not flavor:
            return f"eth{index}"
        
        prefix = flavor.get("interface_prefix", "eth")
        if prefix == "ens":
            # Ubuntu: ens3, ens4, ens5...
            return f"ens{index + 3}"
        else:
            # Cirros: eth0, eth1, eth2...
            return f"eth{index}"

class Interface:
    def __init__(self, name, vlan_id=None, mac=None, ip_config=None, link_id=None):
        self.name = name
        self.vlan_id = vlan_id
        self.mac = mac
        self.ip_config = ip_config
        self.link_id = link_id  # ID del enlace al que pertenece
    def to_dict(self):
        return {"name": self.name, "vlan_id": self.vlan_id, "mac": self.mac, "ip_config": self.ip_config, "link_id": self.link_id}

class Link:
    def __init__(self, link_id, vlan_id, vm1_id, vm1_interface, vm2_id, vm2_interface):
        self.link_id = link_id
        self.vlan_id = vlan_id
        self.vm1_id = vm1_id
        self.vm1_interface = vm1_interface
        self.vm2_id = vm2_id
        self.vm2_interface = vm2_interface
    def to_dict(self):
        return {"link_id": self.link_id, "vlan_id": self.vlan_id, "vm1_id": self.vm1_id, "vm1_interface": self.vm1_interface, "vm2_id": self.vm2_id, "vm2_interface": self.vm2_interface}

class VM:
    def __init__(self, vm_id, name, owner, worker_ip, vnc_port, interfaces, flavor=None, qcow_image=None):
        self.vm_id = vm_id
        self.name = name
        self.owner = owner
        self.worker_ip = worker_ip
        self.vnc_port = vnc_port
        self.interfaces = interfaces
        self.flavor = flavor  # Store flavor name, not spec
        self.qcow_image = qcow_image
        self.status = "design"  # design -> provisioning -> deployed
        self.pid = None
    
    def get_next_interface_name(self):
        """Get next available interface name based on flavor"""
        flavor_spec = Flavor.get(self.flavor)
        if not flavor_spec:
            return None
        
        # Get highest index
        max_index = 0
        for iface in self.interfaces:
            # Extract number from interface name (eth1 -> 1, ens4 -> 4)
            name = iface.name if isinstance(iface, Interface) else iface['name']
            import re
            match = re.search(r'\d+$', name)
            if match:
                idx = int(match.group())
                if flavor_spec['interface_prefix'] == 'ens':
                    # ens3, ens4, ens5... -> indices 0, 1, 2...
                    max_index = max(max_index, idx - 3)
                else:
                    # eth0, eth1, eth2... -> indices 0, 1, 2...
                    max_index = max(max_index, idx)
        
        # Return next interface name
        next_index = max_index + 1
        return Flavor.get_interface_name(self.flavor, next_index)
    
    def add_interface(self, interface):
        """Add a new interface to this VM"""
        self.interfaces.append(interface)
    
    def to_dict(self):
        return {
            "vm_id": self.vm_id,
            "name": self.name,
            "owner": self.owner,
            "worker_ip": self.worker_ip,
            "vnc_port": self.vnc_port,
            "interfaces": [i.to_dict() if isinstance(i, Interface) else i for i in self.interfaces],
            "flavor": self.flavor,
            "qcow_image": self.qcow_image,
            "status": self.status,
            "pid": self.pid
        }

class Network:
    def __init__(self, vlan_id, cidr, gateway_ip, dhcp_enabled=False, dhcp_range=None):
        self.vlan_id = vlan_id
        self.cidr = cidr
        self.gateway_ip = gateway_ip
        self.dhcp_enabled = dhcp_enabled
        self.dhcp_range = dhcp_range
        self.status = "pending"
    def to_dict(self):
        return {"vlan_id": self.vlan_id, "cidr": self.cidr, "gateway_ip": self.gateway_ip, "dhcp_enabled": self.dhcp_enabled, "dhcp_range": self.dhcp_range, "status": self.status}

class Slice:
    def __init__(self, slice_id, owner, topology_type="custom"):
        self.slice_id = slice_id
        self.owner = owner
        self.topology_type = topology_type
        self.vlan_pool_start = 100 + (slice_id % 100) * 20
        self.vlan_pool_end = self.vlan_pool_start + 19
        self.vlan_pool_used = []
        self.vms = []
        self.links = []
        self.networks = []
        self.status = "design"  # design -> running
    
    def get_next_vlan(self):
        for vlan_id in range(self.vlan_pool_start, self.vlan_pool_end + 1):
            if vlan_id not in self.vlan_pool_used:
                self.vlan_pool_used.append(vlan_id)
                return vlan_id
        return None
    
    def add_vm(self, vm):
        self.vms.append(vm)
    
    def add_link(self, link):
        self.links.append(link)
    
    def add_network(self, network):
        self.networks.append(network)
    
    def to_dict(self):
        return {"slice_id": self.slice_id, "owner": self.owner, "topology_type": self.topology_type, "vlan_pool_start": self.vlan_pool_start, "vlan_pool_end": self.vlan_pool_end, "vlan_pool_used": self.vlan_pool_used, "vms": [v.to_dict() for v in self.vms], "links": [l.to_dict() for l in self.links], "networks": [n.to_dict() for n in self.networks], "status": self.status}
