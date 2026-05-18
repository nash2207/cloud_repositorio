"""VLAN Manager - Create/delete VLANs, gateways, DHCP namespaces"""
import subprocess, logging
logger = logging.getLogger(__name__)

class VLANManager:
    def __init__(self, remote_executor, network_node_ip="10.0.10.3"):
        self.executor = remote_executor
        self.network_node_ip = network_node_ip
    
    def create_vlan_with_gateway(self, vlan_id, cidr, gateway_ip, dhcp_enabled=True):
        """Create VLAN with gateway on network node and optional DHCP"""
        try:
            mask = cidr.split('/')[1]
            cmd = f"""
            sudo ovs-vsctl --may-exist add-port br-int gw_vlan{vlan_id} tag={vlan_id} -- set interface gw_vlan{vlan_id} type=internal
            sudo ip addr add {gateway_ip}/{mask} dev gw_vlan{vlan_id} 2>/dev/null || true
            sudo ip link set dev gw_vlan{vlan_id} up
            """
            success, output = self.executor.execute_direct(self.network_node_ip, cmd)
            
            if not success:
                logger.error(f"Gateway creation failed: {output}")
                return False
            
            if dhcp_enabled:
                return self._setup_dhcp(vlan_id, cidr, gateway_ip)
            return success
        except Exception as e:
            logger.error(f"VLAN creation error: {e}")
            return False
    
    def _setup_dhcp(self, vlan_id, cidr, gateway_ip):
        """Setup DHCP namespace with dnsmasq on network node"""
        try:
            ns_name = f"ns-dhcp-vlan{vlan_id}"
            dhcp_port = f"dhcp_v{vlan_id}"
            base_ip = '.'.join(cidr.split('.')[0:3])
            mask = cidr.split('/')[1]
            dhcp_ip = f"{base_ip}.2"
            dhcp_range = f"{base_ip}.10,{base_ip}.250"
            
            cmd = f"""
            sudo ip netns add {ns_name} 2>/dev/null || true
            sudo ovs-vsctl --may-exist add-port br-int {dhcp_port} tag={vlan_id} -- set interface {dhcp_port} type=internal
            sudo ip link set {dhcp_port} netns {ns_name}
            sudo ip netns exec {ns_name} ip addr add {dhcp_ip}/{mask} dev {dhcp_port} 2>/dev/null || true
            sudo ip netns exec {ns_name} ip link set dev lo up
            sudo ip netns exec {ns_name} ip link set dev {dhcp_port} up
            sudo ip netns exec {ns_name} pkill dnsmasq 2>/dev/null || true
            sudo ip netns exec {ns_name} dnsmasq --interface={dhcp_port} --bind-interfaces --dhcp-range={dhcp_range},24h --dhcp-option=3,{gateway_ip} --dhcp-option=6,8.8.8.8
            """
            success, output = self.executor.execute_direct(self.network_node_ip, cmd, timeout=30)
            
            if success:
                logger.info(f"DHCP configured for VLAN {vlan_id} (range: {dhcp_range})")
            else:
                logger.error(f"DHCP setup failed: {output}")
            
            return success
        except Exception as e:
            logger.error(f"DHCP setup error: {e}")
            return False
    
    def enable_internet_for_vlan(self, vlan_id, cidr, outgoing_iface="ens3"):
        """Enable internet access for VLAN via MASQUERADE"""
        try:
            cmd = f"""
            sudo sysctl -w net.ipv4.ip_forward=1
            sudo iptables -t nat -A POSTROUTING -s {cidr} -o {outgoing_iface} -j MASQUERADE 2>/dev/null || true
            sudo iptables -A FORWARD -i gw_vlan{vlan_id} -o {outgoing_iface} -j ACCEPT 2>/dev/null || true
            sudo iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || true
            """
            success, _ = self.executor.execute_direct(self.network_node_ip, cmd)
            if success:
                logger.info(f"Internet enabled for VLAN {vlan_id}")
            return success
        except Exception as e:
            logger.error(f"Internet setup error: {e}")
            return False
    
    def delete_vlan(self, vlan_id):
        """Delete VLAN and cleanup on network node"""
        try:
            cmd = f"""
            sudo ip netns exec ns-dhcp-vlan{vlan_id} pkill dnsmasq 2>/dev/null || true
            sudo ip netns delete ns-dhcp-vlan{vlan_id} 2>/dev/null || true
            sudo ovs-vsctl --if-exists del-port br-int gw_vlan{vlan_id}
            sudo ovs-vsctl --if-exists del-port br-int dhcp_v{vlan_id}
            sudo ip link del gw_vlan{vlan_id} 2>/dev/null || true
            """
            success, _ = self.executor.execute_direct(self.network_node_ip, cmd)
            if success:
                logger.info(f"VLAN {vlan_id} deleted")
            return success
        except Exception as e:
            logger.error(f"VLAN deletion error: {e}")
            return False
