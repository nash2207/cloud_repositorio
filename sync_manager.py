"""Sync Manager - Synchronize worker state with database"""
import logging, re

logger = logging.getLogger(__name__)

class SyncManager:
    def __init__(self, db, remote_executor):
        self.db = db
        self.executor = remote_executor
        self.workers = db.data.get("workers_list", ["10.0.10.1", "10.0.10.2", "10.0.10.3"])
    
    def sync_all_workers(self):
        """Scan all workers and sync VMs with database"""
        logger.info("Starting worker synchronization...")
        
        for worker_ip in self.workers:
            self.sync_worker(worker_ip)
        
        logger.info("Worker synchronization completed")
    
    def sync_worker(self, worker_ip):
        """Sync single worker: detect running VMs and update DB"""
        try:
            # Get running QEMU processes
            cmd = "ps aux | grep 'qemu-system-x86_64.*daemonize' | grep -v grep"
            success, output = self.executor.execute_direct(worker_ip, cmd)
            
            if not success or not output.strip():
                logger.info(f"No VMs running on {worker_ip}")
                return
            
            # Parse QEMU processes
            running_vms = self._parse_qemu_processes(output)
            logger.info(f"Found {len(running_vms)} VMs on {worker_ip}: {[vm['name'] for vm in running_vms]}")
            
            # Check each VM against database
            for vm_info in running_vms:
                self._sync_vm(worker_ip, vm_info)
                
        except Exception as e:
            logger.error(f"Sync error for {worker_ip}: {e}")
    
    def _parse_qemu_processes(self, ps_output):
        """Parse ps output to extract VM information"""
        vms = []
        for line in ps_output.strip().split('\n'):
            try:
                # Extract PID
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
    
    def _sync_vm(self, worker_ip, vm_info):
        """Sync single VM: check if it's in DB, if not it's orphaned"""
        vm_name = vm_info['name']
        pid = vm_info['pid']
        
        # Search for VM in all slices
        found = False
        for slice_id, slice_data in self.db.data.get("slices", {}).items():
            for vm in slice_data.get("vms", []):
                if vm.get("name") == vm_name and vm.get("worker_ip") == worker_ip:
                    # VM found in DB, update PID and status
                    vm["pid"] = pid
                    vm["status"] = "running"
                    self.db.update_slice(slice_id, slice_data)
                    logger.info(f"Synced VM {vm_name} (PID: {pid}) in slice {slice_id}")
                    found = True
                    break
            if found:
                break
        
        if not found:
            logger.warning(f"Orphaned VM detected: {vm_name} (PID: {pid}) on {worker_ip}")
            # Optionally: kill orphaned VMs or register them
            # For now, just log them
    
    def cleanup_orphaned_vms(self):
        """Kill all VMs not registered in database"""
        logger.info("Cleaning up orphaned VMs...")
        
        for worker_ip in self.workers:
            cmd = "ps aux | grep 'qemu-system-x86_64.*daemonize' | grep -v grep"
            success, output = self.executor.execute_direct(worker_ip, cmd)
            
            if not success or not output.strip():
                continue
            
            running_vms = self._parse_qemu_processes(output)
            
            for vm_info in running_vms:
                vm_name = vm_info['name']
                pid = vm_info['pid']
                
                # Check if VM is in database
                found = any(
                    any(vm.get("name") == vm_name and vm.get("worker_ip") == worker_ip 
                        for vm in slice_data.get("vms", []))
                    for slice_data in self.db.data.get("slices", {}).values()
                )
                
                if not found:
                    logger.info(f"Killing orphaned VM: {vm_name} (PID: {pid}) on {worker_ip}")
                    kill_cmd = f"sudo kill -9 {pid}"
                    self.executor.execute_direct(worker_ip, kill_cmd)
                    
                    # Cleanup qcow2 file
                    cleanup_cmd = f"rm -f {vm_info['qcow_path']}"
                    self.executor.execute_direct(worker_ip, cleanup_cmd)
        
        logger.info("Orphaned VM cleanup completed")
