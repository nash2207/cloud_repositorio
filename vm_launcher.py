"""VM Launcher - Start QEMU VMs with proper networking"""
import logging
logger = logging.getLogger(__name__)

class VMLauncher:
    def __init__(self, remote_executor):
        self.executor = remote_executor
    
    def launch_vm(self, worker_ip, vm_dict):
        """Launch QEMU VM on worker with all interfaces"""
        try:
            vm_id = vm_dict["vm_id"]
            vm_name = vm_dict["name"]
            vnc_port = vm_dict["vnc_port"]
            qcow_image = vm_dict.get("qcow_image", "")
            flavor = vm_dict.get("flavor", {})
            interfaces = vm_dict.get("interfaces", [])
            
            cores = flavor.get("cores", 1)
            ram_mb = int(flavor.get("ram_gb", 0.5) * 1024)
            
            # Build QEMU command
            qemu_cmd = f"sudo qemu-system-x86_64 -enable-kvm -m {ram_mb} -smp {cores} "
            qemu_cmd += f"-vnc 0.0.0.0:{vnc_port - 5900} "
            
            # Add network interfaces
            for idx, iface in enumerate(interfaces):
                tap_name = f"tap_{vm_id}_{iface['name']}"
                mac = iface.get("mac", "")
                vlan_id = iface.get("vlan_id")
                
                # Create TAP and connect to OVS
                if vlan_id:
                    tap_cmd = f"""
                    sudo ip tuntap add mode tap name {tap_name}
                    sudo ip link set dev {tap_name} up
                    sudo ovs-vsctl --may-exist add-port br-int {tap_name} tag={vlan_id}
                    """
                    success, _ = self.executor.execute_direct(worker_ip, tap_cmd)
                    if not success:
                        logger.error(f"Failed to create TAP {tap_name}")
                        continue
                    
                    qemu_cmd += f"-netdev tap,id=net{idx},ifname={tap_name},script=no,downscript=no "
                    qemu_cmd += f"-device e1000,netdev=net{idx},mac={mac} "
            
            # Add disk
            if qcow_image:
                qemu_cmd += f"-drive file={qcow_image},format=qcow2 "
            
            qemu_cmd += "-daemonize"
            
            logger.info(f"Launching VM {vm_name} on {worker_ip}: {qemu_cmd}")
            success, output = self.executor.execute_direct(worker_ip, qemu_cmd, timeout=60)
            
            if success:
                # Get PID
                pid_cmd = f"pgrep -f 'qemu.*{vm_name}' | head -1"
                success_pid, pid = self.executor.execute_direct(worker_ip, pid_cmd)
                
                # Configure static IP on eth0 if it's VLAN 400 (internet)
                for iface in interfaces:
                    if iface["name"] == "eth0" and iface.get("vlan_id") == 400:
                        ip_config = iface.get("ip_config", {})
                        static_ip = ip_config.get("ip") if ip_config else None
                        if static_ip:
                            # Wait for VM to boot (5 seconds)
                            import time
                            time.sleep(5)
                            # Note: This would require console access or SSH into VM
                            # For now, just log it - user can configure manually
                            logger.info(f"VM {vm_name} should use static IP {static_ip} on eth0")
                
                return True, pid.strip() if success_pid else None
            else:
                logger.error(f"QEMU launch failed: {output}")
                return False, None
                
        except Exception as e:
            logger.error(f"VM launch error: {e}")
            return False, None
    
    def stop_vm(self, worker_ip, vm_dict):
        """Stop QEMU VM and cleanup TAPs"""
        try:
            vm_id = vm_dict["vm_id"]
            vm_name = vm_dict["name"]
            interfaces = vm_dict.get("interfaces", [])
            
            # Kill QEMU process
            kill_cmd = f"sudo pkill -9 -f 'qemu.*{vm_name}'"
            self.executor.execute_direct(worker_ip, kill_cmd)
            
            # Cleanup TAPs
            for iface in interfaces:
                tap_name = f"tap_{vm_id}_{iface['name']}"
                cleanup_cmd = f"""
                sudo ovs-vsctl --if-exists del-port br-int {tap_name}
                sudo ip link del {tap_name} 2>/dev/null
                """
                self.executor.execute_direct(worker_ip, cleanup_cmd)
            
            logger.info(f"VM {vm_name} stopped on {worker_ip}")
            return True
        except Exception as e:
            logger.error(f"VM stop error: {e}")
            return False
