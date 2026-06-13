"""Sync Manager - Synchronize worker state with database"""
import logging
from providers.baremetal_provider import BareMetalComputeProvider

logger = logging.getLogger(__name__)


class SyncManager:
    """Sync manager with pluggable compute provider"""
    
    def __init__(self, db, remote_executor, compute_provider=None):
        self.db = db
        self.executor = remote_executor
        self.compute_provider = compute_provider or BareMetalComputeProvider(remote_executor)
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
            running_vms = self.compute_provider.get_running_vms(worker_ip)
            
            if not running_vms:
                logger.info(f"No VMs running on {worker_ip}")
                return
            
            logger.info(f"Found {len(running_vms)} VMs on {worker_ip}: {[vm['name'] for vm in running_vms]}")
            
            # Check each VM against database
            for vm_info in running_vms:
                self._sync_vm(worker_ip, vm_info)
                
        except Exception as e:
            logger.error(f"Sync error for {worker_ip}: {e}")
    
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
                    vm["status"] = "deployed"
                    self.db.update_slice(slice_id, slice_data)
                    logger.info(f"Synced VM {vm_name} (PID: {pid}) in slice {slice_id}")
                    found = True
                    break
            if found:
                break
        
        if not found:
            logger.warning(f"Orphaned VM detected: {vm_name} (PID: {pid}) on {worker_ip}")
    
    def cleanup_orphaned_vms(self):
        """Kill all VMs not registered in database and update user quotas"""
        logger.info("Cleaning up orphaned VMs...")
        
        orphaned_count = 0
        
        for worker_ip in self.workers:
            try:
                running_vms = self.compute_provider.get_running_vms(worker_ip)
                
                if not running_vms:
                    logger.info(f"No VMs running on {worker_ip}")
                    continue
                
                logger.info(f"Checking {len(running_vms)} VMs on {worker_ip}")
                
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
                        success, _ = self.executor.execute_direct(worker_ip, kill_cmd)
                        
                        if success:
                            orphaned_count += 1
                            # Cleanup qcow2 file
                            qcow_path = vm_info.get('qcow_path', '')
                            if qcow_path:
                                cleanup_cmd = f"rm -f {qcow_path}"
                                self.executor.execute_direct(worker_ip, cleanup_cmd)
                        else:
                            logger.warning(f"Failed to kill VM {vm_name} on {worker_ip}")
                    else:
                        logger.debug(f"VM {vm_name} is registered in database, skipping")
                        
            except Exception as e:
                logger.error(f"Error processing worker {worker_ip}: {e}")
        
        # Recalculate user VM counts from actual slices
        self._recalculate_user_quotas()
        
        if orphaned_count > 0:
            logger.info(f"Orphaned VM cleanup completed: {orphaned_count} VMs killed")
        else:
            logger.info("Orphaned VM cleanup completed: No orphaned VMs found")
    
    def _recalculate_user_quotas(self):
        """Recalculate used_vms for all users based on actual slices"""
        logger.info("Recalculating user VM quotas...")
        
        for username, user_data in self.db.data.get("users", {}).items():
            slice_ids = user_data.get("slices", [])
            total_vms = 0
            
            for slice_id in slice_ids:
                slice_data = self.db.get_slice(slice_id)
                if slice_data:
                    total_vms += len(slice_data.get("vms", []))
            
            if user_data.get("used_vms", 0) != total_vms:
                logger.info(f"Updating {username}: used_vms {user_data.get('used_vms', 0)} -> {total_vms}")
                user_data["used_vms"] = total_vms
                self.db.update_user(username, user_data)
        
        logger.info("User quota recalculation completed")
