"""VLAN Manager - Create/delete VLANs, gateways, DHCP namespaces"""
import subprocess, logging
logger = logging.getLogger(__name__)

class VLANManager:
    def __init__(self, remote_executor):
        self.executor = remote_executor
    
    def create_vlan_with_gateway(self, worker_ip, vlan_id, cidr, gateway_ip, dhcp_enabled=False):
        """Create VLAN with optional DHCP"""
        try:
            cmd = f"""
            sudo ovs-vsctl add-port br-int gw_vlan{vlan_id} tag={vlan_id} -- set interface gw_vlan{vlan_id} type=internal
            sudo ip addr add {gateway_ip}/{cidr.split('/')[1]} dev gw_vlan{vlan_id}
            sudo ip link set dev gw_vlan{vlan_id} up
            """
            success, _ = self.executor.execute(worker_ip, "", args=[cmd])
            if success and dhcp_enabled:
                return self._setup_dhcp(worker_ip, vlan_id, cidr, gateway_ip)
            return success
        except Exception as e:
            logger.error(f"VLAN creation error: {e}")
            return False
    
    def _setup_dhcp(self, worker_ip, vlan_id, cidr, gateway_ip):
        """Setup DHCP namespace with dnsmasq"""
        try:
            ns_name = f"ns-dhcp-vlan{vlan_id}"
            dhcp_port = f"dhcp_v{vlan_id}"
            base_ip = cidr.split('.')[0:3]
            dhcp_ip = f"{'.'.join(base_ip)}.2"
            dhcp_range = f"{'.'.join(base_ip)}.10,{'.'.join(base_ip)}.15"
            
            cmd = f"""
            sudo ip netns add {ns_name}
            sudo ovs-vsctl add-port br-int {dhcp_port} tag={vlan_id} -- set interface {dhcp_port} type=internal
            sudo ip link set {dhcp_port} netns {ns_name}
            sudo ip netns exec {ns_name} ip addr add {dhcp_ip}/24 dev {dhcp_port}
            sudo ip netns exec {ns_name} ip link set dev {dhcp_port} up
            sudo ip netns exec {ns_name} dnsmasq --interface={dhcp_port} --dhcp-range={dhcp_range},24h --dhcp-option=3,{gateway_ip}
            """
            success, _ = self.executor.execute(worker_ip, "", args=[cmd])
            return success
        except Exception as e:
            logger.error(f"DHCP setup error: {e}")
            return False
    
    def delete_vlan(self, worker_ip, vlan_id):
        """Delete VLAN and cleanup"""
        try:
            cmd = f"""
            sudo pkill -f "ns-dhcp-vlan{vlan_id}"
            sudo ip netns delete ns-dhcp-vlan{vlan_id} 2>/dev/null
            sudo ovs-vsctl del-port br-int gw_vlan{vlan_id} 2>/dev/null
            sudo ip link del gw_vlan{vlan_id} 2>/dev/null
            """
            success, _ = self.executor.execute(worker_ip, "", args=[cmd])
            return success
        except Exception as e:
            logger.error(f"VLAN deletion error: {e}")
            return False
