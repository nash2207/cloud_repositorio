"""OOP Models for Slice Manager R1C+R2 with VLAN support"""
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

class Interface:
    def __init__(self, name, vlan_id=None, mac=None, ip_config=None):
        self.name = name
        self.vlan_id = vlan_id
        self.mac = mac
        self.ip_config = ip_config
    def to_dict(self):
        return {"name": self.name, "vlan_id": self.vlan_id, "mac": self.mac, "ip_config": self.ip_config}

class VM:
    def __init__(self, vm_id, name, owner, worker_ip, vnc_port, interfaces, qcow_image=None):
        self.vm_id = vm_id
        self.name = name
        self.owner = owner
        self.worker_ip = worker_ip
        self.vnc_port = vnc_port
        self.interfaces = interfaces
        self.qcow_image = qcow_image
        self.status = "pending"
        self.pid = None
    def to_dict(self):
        return {"vm_id": self.vm_id, "name": self.name, "owner": self.owner, "worker_ip": self.worker_ip, "vnc_port": self.vnc_port, "interfaces": [i.to_dict() for i in self.interfaces], "qcow_image": self.qcow_image, "status": self.status, "pid": self.pid}

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
    def __init__(self, slice_id, owner, vlan_ids, topology_type="linear"):
        self.slice_id = slice_id
        self.owner = owner
        self.vlan_ids = vlan_ids
        self.topology_type = topology_type
        self.vms = []
        self.networks = []
        self.status = "pending"
    def add_vm(self, vm):
        self.vms.append(vm)
    def add_network(self, network):
        self.networks.append(network)
    def to_dict(self):
        return {"slice_id": self.slice_id, "owner": self.owner, "vlan_ids": self.vlan_ids, "topology_type": self.topology_type, "vms": [v.to_dict() for v in self.vms], "networks": [n.to_dict() for n in self.networks], "status": self.status}
