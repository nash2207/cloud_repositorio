#!/usr/bin/env python3
"""
Test script to diagnose websockify connectivity
"""
import subprocess
import socket
import time
import sys

def check_port_listening(port):
    """Check if a port is listening"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', port))
        sock.close()
        return result == 0
    except Exception as e:
        print(f"Error checking port {port}: {e}")
        return False

def check_websockify_installed():
    """Check if websockify is installed"""
    try:
        result = subprocess.run(['which', 'websockify'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ websockify found at: {result.stdout.strip()}")
            return True
        else:
            print("✗ websockify not found in PATH")
            return False
    except Exception as e:
        print(f"✗ Error checking websockify: {e}")
        return False

def check_vnc_port(worker_ip, vnc_port):
    """Check if VNC port is accessible on worker"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((worker_ip, vnc_port))
        sock.close()
        if result == 0:
            print(f"✓ VNC port {vnc_port} is accessible on {worker_ip}")
            return True
        else:
            print(f"✗ VNC port {vnc_port} is NOT accessible on {worker_ip}")
            return False
    except Exception as e:
        print(f"✗ Error checking VNC port: {e}")
        return False

def test_websockify_start(worker_ip, vnc_port, proxy_port):
    """Test starting websockify"""
    print(f"\nTesting websockify: localhost:{proxy_port} -> {worker_ip}:{vnc_port}")
    
    try:
        cmd = ['websockify', str(proxy_port), f'{worker_ip}:{vnc_port}']
        print(f"Command: {' '.join(cmd)}")
        
        log_file = f'/tmp/test_websockify_{proxy_port}.log'
        with open(log_file, 'w') as logf:
            process = subprocess.Popen(
                cmd,
                stdout=logf,
                stderr=subprocess.STDOUT,
                start_new_session=True
            )
        
        print(f"Started websockify (PID {process.pid}), log: {log_file}")
        
        # Wait for port to be ready
        print("Waiting for port to be ready...")
        for i in range(10):
            if check_port_listening(proxy_port):
                print(f"✓ Port {proxy_port} is now listening")
                
                # Try to read log
                time.sleep(0.5)
                try:
                    with open(log_file, 'r') as f:
                        log_content = f.read()
                        if log_content:
                            print("\nLog output:")
                            print(log_content)
                except Exception as e:
                    print(f"Could not read log: {e}")
                
                # Kill the process
                import os
                os.kill(process.pid, 9)
                print(f"Stopped test websockify (PID {process.pid})")
                return True
            time.sleep(0.5)
        
        print(f"✗ Port {proxy_port} did not start listening after 5 seconds")
        
        # Read log
        try:
            with open(log_file, 'r') as f:
                log_content = f.read()
                if log_content:
                    print("\nLog output:")
                    print(log_content)
        except Exception as e:
            print(f"Could not read log: {e}")
        
        # Kill the process
        import os
        os.kill(process.pid, 9)
        return False
        
    except Exception as e:
        print(f"✗ Error starting websockify: {e}")
        return False

if __name__ == '__main__':
    print("=== WebSockify Connectivity Test ===\n")
    
    # Default test parameters (change these based on your setup)
    worker_ip = "10.0.0.4"
    vnc_port = 5904
    proxy_port = 6080
    
    if len(sys.argv) > 1:
        worker_ip = sys.argv[1]
    if len(sys.argv) > 2:
        vnc_port = int(sys.argv[2])
    if len(sys.argv) > 3:
        proxy_port = int(sys.argv[3])
    
    print(f"Testing with: worker={worker_ip}, vnc_port={vnc_port}, proxy_port={proxy_port}\n")
    
    # Run checks
    print("1. Checking websockify installation...")
    if not check_websockify_installed():
        print("\nInstall websockify: pip install websockify")
        sys.exit(1)
    
    print("\n2. Checking VNC port accessibility...")
    check_vnc_port(worker_ip, vnc_port)
    
    print("\n3. Testing websockify startup...")
    success = test_websockify_start(worker_ip, vnc_port, proxy_port)
    
    if success:
        print("\n✓ All tests passed!")
    else:
        print("\n✗ Some tests failed")
