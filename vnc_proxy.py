"""
VNC Proxy Manager - Manages websockify processes for noVNC access
"""
import logging
import subprocess
import os

logger = logging.getLogger(__name__)


class VNCProxyManager:
    """Manages websockify proxy instances for VNC connections"""
    
    def __init__(self):
        self.proxies = {}  # {proxy_port: {'worker_ip': str, 'vnc_port': int, 'pid': int}}
        self.next_proxy_port = 6080
    
    def get_proxy_port(self, worker_ip, vnc_port):
        """
        Get or create a websockify proxy for a VM's VNC port
        
        Args:
            worker_ip: Worker node IP where VM is running
            vnc_port: VNC port on the worker
        
        Returns:
            int: Local proxy port or None if failed
        """
        # Check if proxy already exists
        for proxy_port, info in self.proxies.items():
            if info['worker_ip'] == worker_ip and info['vnc_port'] == vnc_port:
                logger.info(f"Reusing existing proxy: localhost:{proxy_port} -> {worker_ip}:{vnc_port}")
                return proxy_port
        
        # Create new proxy
        proxy_port = self._find_available_port()
        if not proxy_port:
            logger.error("No available proxy ports")
            return None
        
        try:
            # Start websockify in background
            cmd = [
                'websockify',
                '--web', '/home/ubuntu/cloud/static/novnc',
                str(proxy_port),
                f'{worker_ip}:{vnc_port}'
            ]
            
            # Run in background with nohup
            log_file = f'/tmp/websockify_{proxy_port}.log'
            with open(log_file, 'w') as logf:
                process = subprocess.Popen(
                    cmd,
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    start_new_session=True
                )
            
            self.proxies[proxy_port] = {
                'worker_ip': worker_ip,
                'vnc_port': vnc_port,
                'pid': process.pid
            }
            
            logger.info(f"Started websockify: localhost:{proxy_port} -> {worker_ip}:{vnc_port}")
            logger.info(f"Proxy created: localhost:{proxy_port} -> {worker_ip}:{vnc_port}")
            logger.info(f"Returning console URL: /novnc/vnc.html?path=vnc_ws/{proxy_port}&autoconnect=true&resize=scale")
            
            return proxy_port
            
        except Exception as e:
            logger.error(f"Failed to start websockify: {e}")
            return None
    
    def _find_available_port(self):
        """Find next available proxy port"""
        while self.next_proxy_port < 7000:
            if self.next_proxy_port not in self.proxies:
                port = self.next_proxy_port
                self.next_proxy_port += 1
                return port
            self.next_proxy_port += 1
        return None
    
    def stop_proxy(self, proxy_port):
        """Stop a specific proxy"""
        if proxy_port not in self.proxies:
            return False
        
        try:
            info = self.proxies[proxy_port]
            pid = info['pid']
            
            # Kill process
            os.kill(pid, 9)
            
            del self.proxies[proxy_port]
            logger.info(f"Stopped proxy on port {proxy_port}")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping proxy {proxy_port}: {e}")
            return False
    
    def stop_all(self):
        """Stop all proxies"""
        for proxy_port in list(self.proxies.keys()):
            self.stop_proxy(proxy_port)
        logger.info("All VNC proxies stopped")


# Global instance
vnc_proxy_manager = VNCProxyManager()
