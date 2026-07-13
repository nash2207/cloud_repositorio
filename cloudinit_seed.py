"""
Cloud-Init NoCloud Seed Generator
Generates ISO seed images for automatic VM network configuration
"""
import logging
import yaml
import tempfile
import os

logger = logging.getLogger(__name__)


class CloudInitSeedGenerator:
    """
    Generates cloud-init NoCloud seed images for VM initialization
    
    NoCloud seed format:
    - meta-data: Instance metadata (instance-id, hostname)
    - user-data: Cloud-init configuration (network, users, etc.)
    - Packaged as ISO9660 with volume label 'cidata'
    """
    
    def __init__(self, remote_executor):
        """
        Initialize seed generator
        
        Args:
            remote_executor: RemoteExecutor instance for SSH operations
        """
        self.executor = remote_executor
    
    def generate_seed_iso(self, worker_ip, vm_id, vm_name, interfaces):
        """
        Generate cloud-init seed ISO for a VM
        
        Args:
            worker_ip: Worker node IP where ISO will be created
            vm_id: VM identifier
            vm_name: VM hostname
            interfaces: List of interface dicts with 'name' field
        
        Returns:
            Tuple[bool, str]: (success, iso_path)
        
        Process:
            1. Generate meta-data and user-data YAML
            2. Create temporary directory on worker
            3. Write YAML files
            4. Package into ISO using genisoimage
            5. Return ISO path
        """
        try:
            # Generate cloud-init configuration
            meta_data = self._generate_metadata(vm_id, vm_name)
            user_data = self._generate_userdata(vm_name, interfaces)
            
            # Create seed directory on worker
            seed_dir = f"/tmp/seed_{vm_id}"
            iso_path = f"~/vm_images/{vm_name}_seed.iso"
            
            # Create directory
            cmd = f"mkdir -p {seed_dir}"
            success, _ = self.executor.execute_direct(worker_ip, cmd)
            if not success:
                logger.error(f"Failed to create seed directory on {worker_ip}")
                return False, None
            
            # Write meta-data
            meta_content = yaml.dump(meta_data, default_flow_style=False)
            write_cmd = f"cat > {seed_dir}/meta-data << 'EOFMETA'\n{meta_content}\nEOFMETA"
            success, _ = self.executor.execute_direct(worker_ip, write_cmd)
            if not success:
                logger.error(f"Failed to write meta-data")
                return False, None
            
            # Write user-data
            user_content = self._format_userdata_yaml(user_data)
            write_cmd = f"cat > {seed_dir}/user-data << 'EOFUSER'\n{user_content}\nEOFUSER"
            success, _ = self.executor.execute_direct(worker_ip, write_cmd)
            if not success:
                logger.error(f"Failed to write user-data")
                return False, None
            
            # Generate ISO using genisoimage (or mkisofs)
            # -output: output file
            # -volid: volume label (MUST be 'cidata' for NoCloud)
            # -joliet: Joliet extensions for long filenames
            # -rock: Rock Ridge extensions for POSIX attributes
            iso_cmd = f"""
            genisoimage -output {iso_path} \
                -volid cidata \
                -joliet \
                -rock \
                {seed_dir}/meta-data {seed_dir}/user-data 2>&1 || \
            mkisofs -output {iso_path} \
                -volid cidata \
                -joliet \
                -rock \
                {seed_dir}/meta-data {seed_dir}/user-data 2>&1
            """
            success, output = self.executor.execute_direct(worker_ip, iso_cmd, timeout=30)
            
            if not success:
                logger.error(f"Failed to generate ISO: {output}")
                return False, None
            
            # Cleanup temp directory
            cleanup_cmd = f"rm -rf {seed_dir}"
            self.executor.execute_direct(worker_ip, cleanup_cmd)
            
            logger.info(f"Cloud-init seed ISO created: {iso_path}")
            return True, iso_path
            
        except Exception as e:
            logger.error(f"Seed generation error: {e}")
            return False, None
    
    def _generate_metadata(self, vm_id, vm_name):
        """
        Generate cloud-init meta-data
        
        Args:
            vm_id: VM identifier
            vm_name: VM hostname
        
        Returns:
            dict: meta-data content
        """
        return {
            'instance-id': f'vm-{vm_id}',
            'local-hostname': vm_name
        }
    
    def _generate_userdata(self, vm_name, interfaces):
        """
        Generate cloud-init user-data with network configuration
        
        Args:
            vm_name: VM hostname
            interfaces: List of interface dicts
        
        Returns:
            dict: user-data content (will be converted to YAML)
        """
        # Build network config for all interfaces
        # CRITICAL: Internet interfaces (VLAN 400) use STATIC IP from ip_config
        # Topology interfaces (other VLANs) use DHCP
        ethernets = {}
        for iface in interfaces:
            iface_dict = iface if isinstance(iface, dict) else iface.__dict__
            iface_name = iface_dict.get('name')
            vlan_id = iface_dict.get('vlan_id')
            ip_config = iface_dict.get('ip_config')
            
            # VLAN 400 = Internet interface
            if vlan_id == 400:
                if ip_config:
                    # Has static IP (from previous deployment) - use static config
                    if '/' in ip_config:
                        ip_addr = ip_config  # CIDR notation
                    else:
                        ip_addr = f"{ip_config}/25"  # Add default netmask
                    
                    ethernets[iface_name] = {
                        'dhcp4': False,
                        'dhcp6': False,
                        'addresses': [ip_addr],
                        'routes': [
                            {
                                'to': '0.0.0.0/0',  # Default route
                                'via': '10.60.8.254'  # Gateway
                            }
                        ],
                        'nameservers': {
                            'addresses': ['10.60.8.254', '8.8.8.8']
                        }
                    }
                else:
                    # No IP yet (initial deployment) - use DHCP to get IP from network node
                    ethernets[iface_name] = {
                        'dhcp4': True,
                        'dhcp6': False
                    }
            else:
                # Topology interfaces use DHCP
                ethernets[iface_name] = {
                    'dhcp4': True,
                    'dhcp6': False
                }
        
        network_config = {
            'version': 2,
            'ethernets': ethernets
        }
        
        # Generate netplan YAML content
        netplan_yaml = yaml.dump({'network': network_config}, default_flow_style=False)
        
        # User-data format
        user_data = {
            # Preserve default user (ubuntu:ubuntu)
            'users': [
                'default',  # Keep the default user from the cloud image
            ],
            
            # Allow password authentication (for VNC console)
            'ssh_pwauth': True,
            'chpasswd': {
                'expire': False,
                'list': [
                    'ubuntu:ubuntu'  # Set password for ubuntu user
                ]
            },
            
            # Overwrite existing netplan files to apply our configuration
            'write_files': [
                {
                    'path': '/etc/netplan/50-cloud-init.yaml',
                    'content': netplan_yaml,
                    'permissions': '0644'
                }
            ],
            
            # Set hostname
            'hostname': vm_name,
            'fqdn': f'{vm_name}.local',
            
            # Preserve hostname on reboot
            'manage_etc_hosts': True,
            
            # Run commands on first boot
            'runcmd': [
                # Remove old netplan configs
                'rm -f /etc/netplan/01-netcfg.yaml',
                'rm -f /etc/netplan/00-installer-config.yaml',
                # Apply new netplan configuration
                'netplan generate',
                'netplan apply'
            ]
        }
        
        return user_data
    
    def _format_userdata_yaml(self, user_data):
        """
        Format user-data as cloud-init YAML
        
        Must start with '#cloud-config' header
        
        Args:
            user_data: dict of user-data
        
        Returns:
            str: Formatted YAML string
        """
        yaml_content = yaml.dump(user_data, default_flow_style=False, sort_keys=False)
        return f"#cloud-config\n{yaml_content}"
    
    def delete_seed_iso(self, worker_ip, vm_name):
        """
        Delete cloud-init seed ISO
        
        Args:
            worker_ip: Worker node IP
            vm_name: VM name
        
        Returns:
            bool: Success status
        """
        try:
            iso_path = f"~/vm_images/{vm_name}_seed.iso"
            cmd = f"rm -f {iso_path}"
            success, _ = self.executor.execute_direct(worker_ip, cmd)
            
            if success:
                logger.debug(f"Deleted seed ISO: {iso_path}")
            
            return success
        except Exception as e:
            logger.error(f"Seed deletion error: {e}")
            return False
