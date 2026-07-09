"""
VNC Proxy Manager - Manages websockify processes for noVNC access
"""
import logging
import subprocess
import os
import time
import socket

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
        # Check if proxy already exists AND verify the process is still alive
        for proxy_port, info in self.proxies.items():
            if info['worker_ip'] == worker_ip and info['vnc_port'] == vnc_port:
                # Verify process is still running
                try:
                    os.kill(info['pid'], 0)  # Signal 0 just checks if process exists
                    logger.info(f"Reusing existing proxy: localhost:{proxy_port} -> {worker_ip}:{vnc_port}")
                    return proxy_port
                except OSError:
                    # Process died, remove from tracking
                    logger.warning(f"Proxy process {info['pid']} died, recreating")
                    del self.proxies[proxy_port]
                    break
        
        # Create new proxy
        proxy_port = self._find_available_port()
        if not proxy_port:
            logger.error("No available proxy ports")
            return None
        
        try:
            # Start websockify in background (no --web flag, we're just proxying)
            cmd = [
                'websockify',
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
            
            # Wait for websockify to start listening
            max_wait = 5  # seconds
            start_time = time.time()
            while time.time() - start_time < max_wait:
                try:
                    # Try to connect to the port
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(0.5)
                    result = sock.connect_ex(('localhost', proxy_port))
                    sock.close()
                    if result == 0:
                        # Port is listening
                        break
                except Exception:
                    pass
                time.sleep(0.2)
            else:
                logger.warning(f"websockify on port {proxy_port} may not be ready yet")
            
            self.proxies[proxy_port] = {
                'worker_ip': worker_ip,
                'vnc_port': vnc_port,
                'pid': process.pid
            }
            
            logger.info(f"Started websockify (PID {process.pid}): localhost:{proxy_port} -> {worker_ip}:{vnc_port}")
            
            return proxy_port
            
        except Exception as e:
            logger.error(f"Failed to start websockify: {e}")
            return None
    
    def _find_available_port(self):
        """Find next available proxy port"""
        while self.next_proxy_port < 7000:
            port = self.next_proxy_port
            if port not in self.proxies:
                # Check if port is actually free (no process listening)
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    sock.bind(('localhost', port))
                    sock.close()
                    # Port is free
                    self.next_proxy_port += 1
                    return port
                except OSError:
                    # Port is in use (orphaned process?), skip it
                    logger.warning(f"Port {port} is in use by another process, skipping")
                    self.next_proxy_port += 1
                    continue
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
