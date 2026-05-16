"""Generate cloud-init ISO with static IP config"""
import os, subprocess
class CloudInitGenerator:
    @staticmethod
    def generate_iso(vm_name, mgmt_ip, data_interfaces):
        user_data = f"""#cloud-config
hostname: {vm_name}
fqdn: {vm_name}.local
manage_etc_hosts: true
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: false
      addresses:
        - {mgmt_ip}/24
      gateway4: 10.60.7.1
      nameservers:
        addresses: [8.8.8.8, 8.8.4.4]
"""
        for idx, iface_name in enumerate(data_interfaces, 1):
            user_data += f"""    {iface_name}:
      dhcp4: true
"""
        iso_path = f"/tmp/{vm_name}-init.iso"
        with open(f"/tmp/{vm_name}-user-data", "w") as f:
            f.write(user_data)
        try:
            subprocess.run(f"mkisofs -o {iso_path} -V cidata -joliet -rock /tmp/{vm_name}-user-data", shell=True, check=True)
            return iso_path
        except Exception as e:
            return None
