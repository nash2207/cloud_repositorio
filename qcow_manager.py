"""QCOW Manager - Handle QCOW2 images with backing files"""
import subprocess, logging, os
logger = logging.getLogger(__name__)

class QCOWManager:
    def __init__(self, remote_executor, base_dir="/tmp/vm_images"):
        self.executor = remote_executor
        self.base_dir = base_dir
    
    def create_backing_image(self, worker_ip, vm_name, base_image_path, vlan_ids):
        """Create QCOW2 image with backing file (thin provisioning)"""
        try:
            base_filename = os.path.basename(base_image_path)
            vm_image = f"{vm_name}_img.qcow2"
            
            cmd = f"""
            mkdir -p {self.base_dir}
            if [ ! -f {self.base_dir}/{base_filename} ]; then
                scp -o StrictHostKeyChecking=no ubuntu@10.0.10.4:{base_image_path} {self.base_dir}/
            fi
            cd {self.base_dir}
            qemu-img create -f qcow2 -b {base_filename} -F qcow2 {vm_image}
            """
            success, output = self.executor.execute_direct(worker_ip, cmd)
            return success, f"{self.base_dir}/{vm_image}" if success else None
        except Exception as e:
            logger.error(f"QCOW creation error: {e}")
            return False, None
    
    def get_image_info(self, worker_ip, image_path):
        """Get QCOW2 image info (virtual size, actual size)"""
        try:
            cmd = f"qemu-img info {image_path}"
            success, output = self.executor.execute(worker_ip, "", args=[cmd])
            return success, output if success else None
        except Exception as e:
            logger.error(f"Image info error: {e}")
            return False, None
    
    def delete_image(self, worker_ip, image_path):
        """Delete QCOW2 image"""
        try:
            cmd = f"rm -f {image_path}"
            success, _ = self.executor.execute(worker_ip, "", args=[cmd])
            return success
        except Exception as e:
            logger.error(f"Image deletion error: {e}")
            return False
