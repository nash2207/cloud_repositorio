"""
Bare-Metal Compute Provider - QEMU/KVM implementation
"""
import logging
import re
from providers.base_compute import BaseComputeProvider

logger = logging.getLogger(__name__)


class BareMetalComputeProvider(BaseComputeProvider):
    """Compute provider for bare-metal QEMU/KVM VMs"""
    
    def __init__(self, remote_executor):
        self.executor = remote_executor
    
    def launch_vm(self, worker_ip, vm_dict):
        """Launch QEMU VM on bare-metal worker"""
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
            
            # Add network interfaces with TAP devices
            for idx, iface in enumerate(interfaces):
                tap_name = f"tap_{vm_id}_{iface['name']}"
                mac = iface.get("mac", "")
                vlan_id = iface.get("vlan_id")
                
                # Create TAP and connect to OVS with VLAN tag
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
            
            logger.info(f"Launching VM {vm_name} on {worker_ip}")
            success, output = self.executor.execute_direct(worker_ip, qemu_cmd, timeout=60)
            
            if success:
                # Get PID
                pid_cmd = f"pgrep -f 'qemu.*{vm_name}' | head -1"
                success_pid, pid = self.executor.execute_direct(worker_ip, pid_cmd)
                
                # Log static IP info for eth0/ens3 with VLAN 400
                for iface in interfaces:
                    if iface.get("vlan_id") == 400:
                        ip_config = iface.get("ip_config", {})
                        static_ip = ip_config.get("ip") if ip_config else None
                        if static_ip:
                            logger.info(f"VM {vm_name} should use static IP {static_ip} on {iface['name']}")
                
                return True, pid.strip() if success_pid else None
            else:
                logger.error(f"QEMU launch failed: {output}")
                return False, None
                
        except Exception as e:
            logger.error(f"VM launch error: {e}")
            return False, None
    
    def stop_vm(self, worker_ip, vm_dict):
        """Stop QEMU VM and cleanup TAP interfaces"""
        try:
            vm_id = vm_dict["vm_id"]
            vm_name = vm_dict["name"]
            interfaces = vm_dict.get("interfaces", [])
            
            # Kill QEMU process
            kill_cmd = f"sudo pkill -9 -f 'qemu.*{vm_name}'"
            self.executor.execute_direct(worker_ip, kill_cmd)
            
            # Cleanup TAP devices
            for iface in interfaces:
                tap_name = f"tap_{vm_id}_{iface['name']}"
                cleanup_cmd = f"""
                sudo ovs-vsctl --if-exists del-port br-int {tap_name}
                sudo ip link del {tap_name} 2>/dev/null || true
                """
                self.executor.execute_direct(worker_ip, cleanup_cmd)
            
            logger.info(f"VM {vm_name} stopped on {worker_ip}")
            return True
        except Exception as e:
            logger.error(f"VM stop error: {e}")
            return False
    
    def get_running_vms(self, worker_ip):
        """Scan worker for running QEMU processes"""
        try:
            cmd = "ps aux | grep 'qemu-system-x86_64.*daemonize' | grep -v grep"
            success, output = self.executor.execute_direct(worker_ip, cmd, timeout=10)
            
            if not success:
                # If command fails, it might be because grep found nothing (exit code 1)
                # That's OK, just means no VMs running
                logger.debug(f"No QEMU processes found on {worker_ip}")
                return []
            
            if not output or not output.strip():
                return []
            
            return self._parse_qemu_processes(output)
            
        except Exception as e:
            logger.error(f"Failed to get running VMs on {worker_ip}: {e}")
            return []
    
    def _parse_qemu_processes(self, ps_output):
        """Parse ps output to extract VM information"""
        vms = []
        for line in ps_output.strip().split('\n'):
            try:
                parts = line.split()
                pid = parts[1]
                
                # Extract VM name from qcow2 file
                match = re.search(r'file=([^,\s]+\.qcow2)', line)
                if match:
                    qcow_path = match.group(1)
                    vm_name = qcow_path.split('/')[-1].replace('_img.qcow2', '')
                    
                    # Extract VNC port
                    vnc_match = re.search(r'-vnc [^:]+:(\d+)', line)
                    vnc_port = 5900 + int(vnc_match.group(1)) if vnc_match else None
                    
                    vms.append({
                        'name': vm_name,
                        'pid': pid,
                        'qcow_path': qcow_path,
                        'vnc_port': vnc_port
                    })
            except Exception as e:
                logger.error(f"Failed to parse line: {line[:50]}... Error: {e}")
        
        return vms
