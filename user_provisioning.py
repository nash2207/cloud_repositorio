"""
User Provisioning Service
Handles local user creation with automatic OpenStack tenant provisioning
"""
import logging
import hashlib
from database import Database
from openstack.keystone_client import KeystoneClient

logger = logging.getLogger(__name__)


class UserProvisioningService:
    """
    Service for provisioning users in both local system and OpenStack
    
    Workflow:
    1. Admin creates user in local system
    2. System automatically provisions OpenStack tenant/project/user
    3. Local password != OpenStack password (security isolation)
    4. OpenStack password stored securely in database
    """
    
    def __init__(self, db, openstack_config=None):
        """
        Initialize user provisioning service
        
        Args:
            db: Database instance
            openstack_config: OpenStack configuration dict (optional)
        """
        self.db = db
        self.openstack_enabled = False
        self.keystone_client = None
        
        if openstack_config and openstack_config.get('enabled'):
            try:
                self.keystone_client = KeystoneClient(
                    keystone_url=openstack_config.get('keystone_url', 'http://controller:5000'),
                    admin_user=openstack_config.get('admin_user', 'admin'),
                    admin_password=openstack_config.get('admin_password', 'admin')
                )
                self.openstack_enabled = True
                logger.info("OpenStack integration enabled")
            except Exception as e:
                logger.warning(f"OpenStack integration disabled: {e}")
    
    def create_user(self, username, password, role="student", quota_vms=10):
        """
        Create user in local system and provision OpenStack tenant
        
        IMPORTANT: If OpenStack provisioning fails, user creation is rolled back
        
        Args:
            username: Local username
            password: Local password (hashed before storage)
            role: User role (admin/student)
            quota_vms: VM quota
        
        Returns:
            Tuple[bool, dict]: (success, user_data) or (False, error_message)
        """
        try:
            # Check if user already exists
            existing_user = self.db.get_user(username)
            if existing_user:
                return False, "User already exists"
            
            # Hash local password
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            
            # Create local user data structure
            user_data = {
                "username": username,
                "password_hash": password_hash,
                "role": role,
                "quota_vms": quota_vms,
                "used_vms": 0,
                "slices": []
            }
            
            # Provision OpenStack tenant if enabled (REQUIRED - fail if it fails)
            if self.openstack_enabled and self.keystone_client:
                logger.info(f"Provisioning OpenStack tenant for user '{username}'...")
                
                success, result = self.keystone_client.provision_tenant(
                    username=username,
                    local_password=password,  # Not used in OpenStack
                    description=f"Tenant for {username}"
                )
                
                if success:
                    # Store OpenStack credentials in user data
                    user_data["openstack"] = {
                        "project_id": result['project_id'],
                        "project_name": result['project_name'],
                        "user_id": result['user_id'],
                        "password": result['openstack_password']  # Auto-generated UUID
                    }
                    logger.info(f"OpenStack tenant provisioned: project={result['project_name']}, user_id={result['user_id']}")
                else:
                    # ROLLBACK: Do not create user if OpenStack provisioning fails
                    error_msg = f"OpenStack provisioning failed: {result}"
                    logger.error(error_msg)
                    logger.error(f"User '{username}' creation aborted (OpenStack integration required)")
                    return False, f"User creation failed: {error_msg}"
            
            # Save user to database only if OpenStack provisioning succeeded (or is disabled)
            self.db.add_user(user_data)
            
            logger.info(f"User '{username}' created successfully (role={role}, quota={quota_vms} VMs)")
            
            return True, user_data
            
        except Exception as e:
            error_msg = f"User creation error: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    def get_user_openstack_credentials(self, username):
        """
        Get OpenStack credentials for a user
        
        Args:
            username: Username
        
        Returns:
            dict: OpenStack credentials or None
        """
        user = self.db.get_user(username)
        if not user:
            return None
        
        return user.get("openstack")
    
    def test_openstack_connection(self):
        """
        Test OpenStack connection by authenticating as admin
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        if not self.openstack_enabled or not self.keystone_client:
            return False, "OpenStack integration not enabled"
        
        try:
            success, result = self.keystone_client.get_admin_token()
            if success:
                return True, f"OpenStack connection successful (token: {result[:20]}...)"
            else:
                return False, f"OpenStack authentication failed: {result}"
        except Exception as e:
            return False, f"OpenStack connection error: {e}"


def provision_user_with_openstack(db, username, password, role="student", quota_vms=10):
    """
    Convenience function for user provisioning with OpenStack integration
    
    Args:
        db: Database instance
        username: Username
        password: Password
        role: User role
        quota_vms: VM quota
    
    Returns:
        Tuple[bool, dict]: (success, user_data) or (False, error_message)
    """
    # Load OpenStack config from database
    openstack_config = db.data.get('openstack', {})
    
    # Create provisioning service
    service = UserProvisioningService(db, openstack_config)
    
    # Provision user
    return service.create_user(username, password, role, quota_vms)
