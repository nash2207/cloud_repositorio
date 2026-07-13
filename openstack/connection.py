"""
OpenStack Connection Factory
Creates authenticated OpenStack SDK connections using environment or config
"""
import os
import logging

logger = logging.getLogger(__name__)

# Import OpenStack SDK with proper error handling
try:
    import openstack
    HAS_OPENSTACK = True
except ImportError as e:
    HAS_OPENSTACK = False
    logger.error(f"OpenStack SDK not available: {e}")


def create_admin_connection(auth_url=None, admin_username=None, admin_password=None, admin_project=None):
    """
    Create an administrative OpenStack connection using SDK
    
    This creates a connection with admin credentials that can be used
    to create networks, launch VMs, etc. across all projects.
    
    Args:
        auth_url: Keystone URL (default: from env OS_AUTH_URL or 10.60.8.1:5000)
        admin_username: Admin username (default: from env OS_USERNAME or "admin")
        admin_password: Admin password (default: from env OS_PASSWORD)
        admin_project: Admin project (default: from env OS_PROJECT_NAME or "admin")
    
    Returns:
        openstack.connection.Connection object
    
    Raises:
        RuntimeError: If connection cannot be established
    """
    if not HAS_OPENSTACK:
        raise RuntimeError(
            "OpenStack SDK not installed. Run: pip install openstacksdk"
        )
    
    # Use provided values or fall back to environment variables or defaults
    auth_url = auth_url or os.environ.get("OS_AUTH_URL", "http://10.60.8.1:5000/v3")
    admin_username = admin_username or os.environ.get("OS_USERNAME", "admin")
    admin_password = admin_password or os.environ.get("OS_PASSWORD")
    admin_project = admin_project or os.environ.get("OS_PROJECT_NAME", "admin")
    
    if not admin_password:
        raise RuntimeError(
            "OpenStack admin password not provided. "
            "Set OS_PASSWORD environment variable or provide admin_password parameter."
        )
    
    logger.info(f"Creating OpenStack connection to {auth_url} as {admin_username}")
    
    try:
        # Create connection using OpenStack SDK
        conn = openstack.connect(
            auth_url=auth_url,
            project_name=admin_project,
            username=admin_username,
            password=admin_password,
            user_domain_name="default",
            project_domain_name="default",
            app_name="slice-manager",
            app_version="1.0",
        )
        
        # Verify connection by authorizing
        conn.authorize()
        
        logger.info("OpenStack connection established successfully")
        return conn
        
    except Exception as e:
        raise RuntimeError(f"Failed to create OpenStack connection: {e}")


def create_project_connection(auth_url, project_id, username, password):
    """
    Create a scoped OpenStack connection for a specific project/tenant
    
    This is used when deploying VMs as a specific user in their project,
    ensuring proper quota enforcement and resource isolation.
    
    Args:
        auth_url: Keystone URL
        project_id: OpenStack project/tenant ID
        username: User's OpenStack username
        password: User's OpenStack password
    
    Returns:
        openstack.connection.Connection object
    
    Raises:
        RuntimeError: If connection cannot be established
    """
    if not HAS_OPENSTACK:
        raise RuntimeError(
            "OpenStack SDK not installed. Run: pip install openstacksdk"
        )
    
    logger.info(f"Creating scoped connection for project {project_id}")
    
    try:
        conn = openstack.connect(
            auth_url=auth_url,
            project_id=project_id,
            username=username,
            password=password,
            user_domain_name="default",
            project_domain_name="default",
            app_name="slice-manager",
            app_version="1.0",
        )
        
        conn.authorize()
        
        logger.info(f"Scoped connection established for project {project_id}")
        return conn
        
    except Exception as e:
        raise RuntimeError(f"Failed to create scoped connection: {e}")

