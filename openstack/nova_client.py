"""
Nova Compute Client - Native REST API
Handles instance creation, hot-plug interfaces, and soft reboot for OpenStack

🚧 STUB - TO BE COMPLETED IN FUTURE IMPLEMENTATION 🚧

INSTANCE DEPLOYMENT FLOW (as per Lab 6 requirements):
1. Create Instance (Boot VM)
   - POST http://10.0.1.1:8774/v2.1/servers
   - Headers: X-Auth-Token: <scoped_token>
   - Payload: {
       "server": {
         "name": "vm1",
         "flavorRef": "<flavor_id>",
         "imageRef": "<image_id>",
         "networks": [{"port": "<port_id_eth0>"}, {"port": "<port_id_eth1>"}],
         "availability_zone": "nova"
       }
     }
   - Returns: server_id, status

2. Hot-Plug Interface (Add interface to running VM)
   - POST http://10.0.1.1:8774/v2.1/servers/{server_id}/os-interface
   - Headers: X-Auth-Token: <scoped_token>
   - Payload: {"interfaceAttachment": {"port_id": "<port_id>"}}
   - For Cirros VMs: Must follow with soft reboot to activate interface

3. Soft Reboot (for Cirros interface activation)
   - POST http://10.0.1.1:8774/v2.1/servers/{server_id}/action
   - Headers: X-Auth-Token: <scoped_token>
   - Payload: {"reboot": {"type": "SOFT"}}
   - Wait ~2 seconds for Cirros to re-read PCI bus and configure interface

4. Get Instance Details
   - GET http://10.0.1.1:8774/v2.1/servers/{server_id}
   - Headers: X-Auth-Token: <scoped_token>
   - Returns: status, addresses, metadata

5. Delete Instance
   - DELETE http://10.0.1.1:8774/v2.1/servers/{server_id}
   - Headers: X-Auth-Token: <scoped_token>

IMPORTANT NOTES:
- Cirros requires soft reboot after hot-plug due to lack of dynamic udev
- Ubuntu/other images handle hot-plug cleanly without reboot
- Use Nova availability zones for placement (default: "nova")
- Flavor and image IDs must be pre-discovered via Glance and Nova APIs
"""

import requests
import logging
import time

logger = logging.getLogger(__name__)


class NovaClient:
    """
    Nova v2.1 Compute Client
    
    TODO - COMPLETE IMPLEMENTATION:
    - Implement create_instance() with port_ids for network configuration
    - Implement attach_interface() for hot-plug operations
    - Implement soft_reboot() specifically for Cirros VMs
    - Implement get_instance() to check status and IP addresses
    - Implement delete_instance() for cleanup
    - Implement list_flavors() to discover available flavors
    - Add polling logic for instance status (ACTIVE, ERROR states)
    - Add error handling for HTTP status codes (400, 401, 404, 409 conflict)
    - Handle token expiration with retry logic
    """
    
    def __init__(self, nova_url="http://10.0.1.1:8774"):
        self.nova_url = nova_url
    
    def create_instance(self, token, project_id, name, flavor_id, image_id, port_ids, availability_zone="nova"):
        """
        TODO: Create Nova instance with pre-created ports
        Returns: (success, {"server_id": str, "status": str}) or (False, error_message)
        """
        logger.warning(f"NovaClient.create_instance({name}) - STUB NOT IMPLEMENTED")
        return False, "NovaClient not implemented yet"
    
    def attach_interface(self, token, server_id, port_id):
        """
        TODO: Hot-plug interface to running instance
        Returns: (success, interface_dict) or (False, error_message)
        """
        logger.warning(f"NovaClient.attach_interface({server_id}) - STUB NOT IMPLEMENTED")
        return False, "NovaClient not implemented yet"
    
    def soft_reboot(self, token, server_id):
        """
        TODO: Perform soft reboot (needed for Cirros after hot-plug)
        Returns: (success, None) or (False, error_message)
        """
        logger.warning(f"NovaClient.soft_reboot({server_id}) - STUB NOT IMPLEMENTED")
        return False, "NovaClient not implemented yet"
    
    def get_instance(self, token, server_id):
        """
        TODO: Get instance details (status, IPs, ports)
        Returns: (success, instance_dict) or (False, error_message)
        """
        logger.warning(f"NovaClient.get_instance({server_id}) - STUB NOT IMPLEMENTED")
        return False, "NovaClient not implemented yet"
    
    def delete_instance(self, token, server_id):
        """
        TODO: Delete instance
        Returns: (success, None) or (False, error_message)
        """
        logger.warning(f"NovaClient.delete_instance({server_id}) - STUB NOT IMPLEMENTED")
        return False, "NovaClient not implemented yet"
    
    def list_flavors(self, token):
        """
        TODO: List available flavors
        Returns: (success, [flavor_dict, ...]) or (False, error_message)
        """
        logger.warning(f"NovaClient.list_flavors() - STUB NOT IMPLEMENTED")
        return False, "NovaClient not implemented yet"
    
    def wait_for_active(self, token, server_id, timeout=300, poll_interval=5):
        """
        TODO: Poll instance until status=ACTIVE or ERROR
        Returns: (success, status) or (False, error_message)
        """
        logger.warning(f"NovaClient.wait_for_active({server_id}) - STUB NOT IMPLEMENTED")
        return False, "NovaClient not implemented yet"
