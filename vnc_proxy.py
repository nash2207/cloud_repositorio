"""
VNC WebSocket Proxy Manager
Manages websockify proxies for VNC connections to VMs on different workers
"""
import subprocess
import logging
import os
import signal

logger = logging.getLogger(__name__)


class VNCProxyManager:
    """
    Manages websockify processes for VNC access to VMs
    Creates one proxy per worker:VM combination
    """
    
    def __init__(self, base_port=6080):
        self.base_port = base_port
        self.proxies = {}  # {worker_ip: {vnc_port: proxy_port}}
        self.processes = {}  # {proxy_port: subprocess}
    
    def get_proxy_port(self, worker_ip, vnc_port):
        """
        Get or create websockify proxy for worker:vnc_port
        Returns proxy port on localhost
        """
        if worker_ip not in self.proxies:
            self.proxies[worker_ip] = {}
        
        if vnc_port in self.proxies[worker_ip]:
            return self.proxies[worker_ip][vnc_port]
        
        # Allocate new proxy port
        proxy_port = self._get_next_available_port()
        
        # Start websockify
        success = self._start_websockify(proxy_port, worker_ip, vnc_port)
        
        if success:
            self.proxies[worker_ip][vnc_port] = proxy_port
            logger.info(f"Started websockify: localhost:{proxy_port} -> {worker_ip}:{vnc_port}")
            return proxy_port
        else:
            logger.error(f"Failed to start websockify for {worker_ip}:{vnc_port}")
            return None
    
    def _get_next_available_port(self):
        """Find next available proxy port"""
        used_ports = set(self.processes.keys())
        port = self.base_port
        while port in used_ports:
            port += 1
        return port
    
    def _start_websockify(self, proxy_port, target_host, target_port):
        """Start websockify process"""
        try:
            # Get absolute path to novnc directory
            import os
            base_dir = os.path.dirname(os.path.abspath(__file__))
            novnc_dir = os.path.join(base_dir, "static", "novnc")
            
            if not os.path.exists(novnc_dir):
                logger.error(f"noVNC directory not found: {novnc_dir}")
                return False
            
            cmd = [
                "websockify",
                "--web", novnc_dir,  # Use absolute path
                str(proxy_port),
                f"{target_host}:{target_port}"
            ]
            
            logger.info(f"Starting websockify: {' '.join(cmd)}")
            
            # Start in background with output redirected to log
            log_file = open(f"/tmp/websockify_{proxy_port}.log", "w")
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True  # Detach from parent
            )
            
            # Give it a moment to start
            import time
            time.sleep(0.5)
            
            # Check if it's still running
            if process.poll() is not None:
                logger.error(f"websockify failed to start, check /tmp/websockify_{proxy_port}.log")
                return False
            
            self.processes[proxy_port] = process
            logger.info(f"websockify started with PID {process.pid}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start websockify: {e}")
            return False
    
    def stop_proxy(self, proxy_port):
        """Stop websockify proxy"""
        if proxy_port in self.processes:
            try:
                process = self.processes[proxy_port]
                process.terminate()
                process.wait(timeout=5)
                del self.processes[proxy_port]
                logger.info(f"Stopped websockify on port {proxy_port}")
            except Exception as e:
                logger.error(f"Error stopping websockify: {e}")
    
    def stop_all(self):
        """Stop all websockify proxies"""
        for proxy_port in list(self.processes.keys()):
            self.stop_proxy(proxy_port)
    
    def cleanup_for_worker(self, worker_ip):
        """Stop all proxies for a specific worker"""
        if worker_ip in self.proxies:
            for vnc_port, proxy_port in self.proxies[worker_ip].items():
                self.stop_proxy(proxy_port)
            del self.proxies[worker_ip]


# Global proxy manager instance
vnc_proxy_manager = VNCProxyManager()
