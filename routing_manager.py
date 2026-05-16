"""Routing Manager - iptables rules, MASQUERADE, inter-VLAN"""
import subprocess, logging
logger = logging.getLogger(__name__)

class RoutingManager:
    def __init__(self, remote_executor):
        self.executor = remote_executor
    
    def enable_ip_forward(self, worker_ip):
        """Enable IP forwarding on worker"""
        try:
            cmd = "sudo sysctl -w net.ipv4.ip_forward=1"
            success, _ = self.executor.execute(worker_ip, "", args=[cmd])
            return success
        except Exception as e:
            logger.error(f"IP forward error: {e}")
            return False
    
    def setup_masquerade(self, worker_ip, vlan_id, cidr, outgoing_iface="ens3"):
        """Setup MASQUERADE for internet access"""
        try:
            cmd = f"""
            sudo iptables -t nat -A POSTROUTING -s {cidr} -o {outgoing_iface} -j MASQUERADE
            sudo iptables -A FORWARD -i gw_vlan{vlan_id} -o {outgoing_iface} -j ACCEPT
            sudo iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
            sudo iptables -P FORWARD DROP
            """
            success, _ = self.executor.execute(worker_ip, "", args=[cmd])
            return success
        except Exception as e:
            logger.error(f"Masquerade setup error: {e}")
            return False
    
    def route_between_vlans(self, worker_ip, vlan1_id, vlan2_id):
        """Enable routing between two VLANs"""
        try:
            cmd = f"""
            sudo iptables -A FORWARD -i gw_vlan{vlan1_id} -o gw_vlan{vlan2_id} -j ACCEPT
            sudo iptables -A FORWARD -i gw_vlan{vlan2_id} -o gw_vlan{vlan1_id} -j ACCEPT
            """
            success, _ = self.executor.execute(worker_ip, "", args=[cmd])
            return success
        except Exception as e:
            logger.error(f"VLAN routing error: {e}")
            return False
    
    def delete_masquerade(self, worker_ip, vlan_id, cidr, outgoing_iface="ens3"):
        """Remove MASQUERADE rules"""
        try:
            cmd = f"""
            sudo iptables -t nat -D POSTROUTING -s {cidr} -o {outgoing_iface} -j MASQUERADE 2>/dev/null
            sudo iptables -D FORWARD -i gw_vlan{vlan_id} -o {outgoing_iface} -j ACCEPT 2>/dev/null
            """
            success, _ = self.executor.execute(worker_ip, "", args=[cmd])
            return success
        except Exception as e:
            logger.error(f"Masquerade deletion error: {e}")
            return False
