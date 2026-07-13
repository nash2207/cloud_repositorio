"""
OpenStack Resource Mapper
Maps local flavor names and image paths to OpenStack Glance images and Nova flavors
"""
import logging

logger = logging.getLogger(__name__)


class OpenStackResourceMapper:
    """
    Maps between local flavor definitions and OpenStack resources
    
    Responsibilities:
    - Convert local flavor names (e.g., "ubuntu") to Nova flavor IDs
    - Convert local image paths to Glance image IDs
    - Cache mappings to reduce API calls
    """
    
    def __init__(self, connection):
        """
        Initialize mapper with OpenStack connection
        
        Args:
            connection: OpenStack SDK connection
        """
        self.connection = connection
        self._image_cache = {}
        self._flavor_cache = {}
    
    def get_image_id(self, local_flavor_name):
        """
        Get Glance image ID for a local flavor name
        
        This searches for images by name matching common patterns:
        - "ubuntu" -> searches for images with "ubuntu" in name
        - Falls back to first available image if no match
        
        Args:
            local_flavor_name: Local flavor name (e.g., "ubuntu", "cirros")
        
        Returns:
            str: Glance image ID (UUID) or None if not found
        """
        if local_flavor_name in self._image_cache:
            return self._image_cache[local_flavor_name]
        
        try:
            logger.info(f"Searching Glance for image matching flavor '{local_flavor_name}'")
            
            # Search for images matching the flavor name
            images = list(self.connection.image.images())
            
            # Try exact name match first
            for img in images:
                if img.name and local_flavor_name.lower() in img.name.lower():
                    logger.info(f"Found image: {img.name} (ID: {img.id})")
                    self._image_cache[local_flavor_name] = img.id
                    return img.id
            
            # If no match, use first available image
            if images:
                img = images[0]
                logger.warning(f"No exact match for '{local_flavor_name}', using first image: {img.name} (ID: {img.id})")
                self._image_cache[local_flavor_name] = img.id
                return img.id
            
            logger.error(f"No images found in Glance")
            return None
            
        except Exception as e:
            logger.error(f"Failed to get image ID: {e}")
            return None
    
    def get_flavor_id(self, local_flavor_name):
        """
        Get Nova flavor ID for a local flavor name
        
        Maps local flavor specs (cores, RAM, disk) to closest Nova flavor:
        - "ubuntu" (1 core, 0.5GB RAM, 2.5GB disk) -> small flavor
        - "cirros" (1 core, 0.5GB RAM, 1GB disk) -> tiny flavor
        
        Args:
            local_flavor_name: Local flavor name
        
        Returns:
            str: Nova flavor ID or name
        """
        if local_flavor_name in self._flavor_cache:
            return self._flavor_cache[local_flavor_name]
        
        try:
            logger.info(f"Searching Nova for flavor matching '{local_flavor_name}'")
            
            # Import local flavor specs to match
            from models import Flavor
            local_flavor_spec = Flavor.get(local_flavor_name)
            
            if not local_flavor_spec:
                logger.error(f"Local flavor '{local_flavor_name}' not found")
                return None
            
            required_cores = local_flavor_spec.get("cores", 1)
            required_ram_gb = local_flavor_spec.get("ram_gb", 0.5)
            required_disk_gb = local_flavor_spec.get("disk_gb", 1)
            
            logger.info(f"Looking for flavor with: {required_cores} cores, {required_ram_gb}GB RAM, {required_disk_gb}GB disk")
            
            # Get all Nova flavors
            flavors = list(self.connection.compute.flavors())
            
            # Find best match (cores and RAM >= required, smallest disk)
            best_match = None
            for flavor in flavors:
                # Nova RAM is in MB, convert to GB
                flavor_ram_gb = flavor.ram / 1024.0
                flavor_disk_gb = flavor.disk
                
                # Check if flavor meets requirements
                if flavor.vcpus >= required_cores and flavor_ram_gb >= required_ram_gb:
                    if best_match is None or flavor_disk_gb < best_match.disk:
                        best_match = flavor
            
            if best_match:
                logger.info(f"Selected flavor: {best_match.name} (ID: {best_match.id}, {best_match.vcpus} cores, {best_match.ram}MB RAM, {best_match.disk}GB disk)")
                self._flavor_cache[local_flavor_name] = best_match.id
                return best_match.id
            
            # If no match, use first available flavor
            if flavors:
                flavor = flavors[0]
                logger.warning(f"No exact match, using first flavor: {flavor.name} (ID: {flavor.id})")
                self._flavor_cache[local_flavor_name] = flavor.id
                return flavor.id
            
            logger.error(f"No flavors found in Nova")
            return None
            
        except Exception as e:
            logger.error(f"Failed to get flavor ID: {e}")
            return None
    
    def list_images(self):
        """
        List all available Glance images
        
        Returns:
            list: List of dicts with keys: id, name, status, size
        """
        try:
            images = list(self.connection.image.images())
            return [
                {
                    "id": img.id,
                    "name": img.name,
                    "status": img.status,
                    "size": getattr(img, "size", 0),
                }
                for img in images
            ]
        except Exception as e:
            logger.error(f"Failed to list images: {e}")
            return []
    
    def list_flavors(self):
        """
        List all available Nova flavors
        
        Returns:
            list: List of dicts with keys: id, name, vcpus, ram_mb, disk_gb
        """
        try:
            flavors = list(self.connection.compute.flavors())
            return [
                {
                    "id": f.id,
                    "name": f.name,
                    "vcpus": f.vcpus,
                    "ram_mb": f.ram,
                    "disk_gb": f.disk,
                }
                for f in flavors
            ]
        except Exception as e:
            logger.error(f"Failed to list flavors: {e}")
            return []
