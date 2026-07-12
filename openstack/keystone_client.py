"""
Keystone Authentication Client - Native REST API
Handles tenant/project provisioning and authentication for OpenStack
"""

import requests
import logging
import uuid

logger = logging.getLogger(__name__)


class KeystoneClient:
    """
    Keystone v3 Authentication Client
    
    Handles:
    - Admin authentication (system-scoped)
    - Project/tenant creation
    - User creation with auto-generated OpenStack passwords
    - Role assignment (member role)
    - Quota management via Nova/Neutron APIs
    """
    
    def __init__(self, keystone_url="http://controller:5000", admin_user="admin", admin_password="admin"):
        """
        Initialize Keystone client
        
        Args:
            keystone_url: Keystone endpoint URL (default: http://controller:5000)
            admin_user: Admin username (default: admin)
            admin_password: Admin password
        """
        self.keystone_url = keystone_url.rstrip('/')
        self.admin_user = admin_user
        self.admin_password = admin_password
        self.admin_token = None
        self.default_domain_id = "default"
        
    def get_admin_token(self):
        """
        Authenticate as admin and get system-scoped token
        
        Returns:
            Tuple[bool, str]: (success, token) or (False, error_message)
        """
        try:
            url = f"{self.keystone_url}/v3/auth/tokens"
            payload = {
                "auth": {
                    "identity": {
                        "methods": ["password"],
                        "password": {
                            "user": {
                                "name": self.admin_user,
                                "domain": {"name": "Default"},
                                "password": self.admin_password
                            }
                        }
                    },
                    "scope": {
                        "system": {"all": True}
                    }
                }
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 201:
                token = response.headers.get('X-Subject-Token')
                self.admin_token = token
                logger.info(f"Admin authentication successful")
                return True, token
            else:
                error_msg = f"Admin authentication failed: HTTP {response.status_code}"
                logger.error(error_msg)
                return False, error_msg
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Admin authentication connection error: {e}"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Admin authentication error: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    def create_project(self, project_name, description=""):
        """
        Create project in default domain
        
        Args:
            project_name: Project name (e.g., "tenant_student1")
            description: Project description (optional)
        
        Returns:
            Tuple[bool, str]: (success, project_id) or (False, error_message)
        """
        try:
            if not self.admin_token:
                success, result = self.get_admin_token()
                if not success:
                    return False, f"Cannot get admin token: {result}"
            
            url = f"{self.keystone_url}/v3/projects"
            headers = {"X-Auth-Token": self.admin_token}
            payload = {
                "project": {
                    "name": project_name,
                    "domain_id": self.default_domain_id,
                    "description": description,
                    "enabled": True
                }
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 201:
                project_id = response.json()['project']['id']
                logger.info(f"Project '{project_name}' created: {project_id}")
                return True, project_id
            elif response.status_code == 409:
                # Project already exists, get its ID
                logger.warning(f"Project '{project_name}' already exists, fetching ID...")
                return self.get_project_id(project_name)
            else:
                error_msg = f"Project creation failed: HTTP {response.status_code} - {response.text}"
                logger.error(error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Project creation error: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    def get_project_id(self, project_name):
        """
        Get project ID by name
        
        Args:
            project_name: Project name
        
        Returns:
            Tuple[bool, str]: (success, project_id) or (False, error_message)
        """
        try:
            if not self.admin_token:
                success, result = self.get_admin_token()
                if not success:
                    return False, f"Cannot get admin token: {result}"
            
            url = f"{self.keystone_url}/v3/projects?name={project_name}"
            headers = {"X-Auth-Token": self.admin_token}
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                projects = response.json().get('projects', [])
                if projects:
                    project_id = projects[0]['id']
                    return True, project_id
                else:
                    return False, f"Project '{project_name}' not found"
            else:
                error_msg = f"Get project failed: HTTP {response.status_code}"
                logger.error(error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Get project error: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    def create_user(self, username, openstack_password=None, description=""):
        """
        Create user in default domain with auto-generated OpenStack password
        
        Args:
            username: Username
            openstack_password: OpenStack password (auto-generated if None)
            description: User description (optional)
        
        Returns:
            Tuple[bool, dict]: (success, {user_id, password}) or (False, error_message)
        """
        try:
            if not self.admin_token:
                success, result = self.get_admin_token()
                if not success:
                    return False, f"Cannot get admin token: {result}"
            
            # Generate strong random password if not provided
            if not openstack_password:
                openstack_password = str(uuid.uuid4())
            
            url = f"{self.keystone_url}/v3/users"
            headers = {"X-Auth-Token": self.admin_token}
            payload = {
                "user": {
                    "name": username,
                    "domain_id": self.default_domain_id,
                    "password": openstack_password,
                    "description": description,
                    "enabled": True
                }
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 201:
                user_id = response.json()['user']['id']
                logger.info(f"User '{username}' created: {user_id}")
                return True, {"user_id": user_id, "password": openstack_password}
            elif response.status_code == 409:
                # User already exists, get its ID
                logger.warning(f"User '{username}' already exists, fetching ID...")
                success, user_id = self.get_user_id(username)
                if success:
                    return True, {"user_id": user_id, "password": openstack_password}
                else:
                    return False, user_id
            else:
                error_msg = f"User creation failed: HTTP {response.status_code} - {response.text}"
                logger.error(error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"User creation error: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    def get_user_id(self, username):
        """
        Get user ID by name
        
        Args:
            username: Username
        
        Returns:
            Tuple[bool, str]: (success, user_id) or (False, error_message)
        """
        try:
            if not self.admin_token:
                success, result = self.get_admin_token()
                if not success:
                    return False, f"Cannot get admin token: {result}"
            
            url = f"{self.keystone_url}/v3/users?name={username}"
            headers = {"X-Auth-Token": self.admin_token}
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                users = response.json().get('users', [])
                if users:
                    user_id = users[0]['id']
                    return True, user_id
                else:
                    return False, f"User '{username}' not found"
            else:
                error_msg = f"Get user failed: HTTP {response.status_code}"
                logger.error(error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Get user error: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    def get_role_id(self, role_name="member"):
        """
        Get role ID by name
        
        Args:
            role_name: Role name (default: member)
        
        Returns:
            Tuple[bool, str]: (success, role_id) or (False, error_message)
        """
        try:
            if not self.admin_token:
                success, result = self.get_admin_token()
                if not success:
                    return False, f"Cannot get admin token: {result}"
            
            url = f"{self.keystone_url}/v3/roles?name={role_name}"
            headers = {"X-Auth-Token": self.admin_token}
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                roles = response.json().get('roles', [])
                if roles:
                    role_id = roles[0]['id']
                    return True, role_id
                else:
                    return False, f"Role '{role_name}' not found"
            else:
                error_msg = f"Get role failed: HTTP {response.status_code}"
                logger.error(error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Get role error: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    def assign_role(self, project_id, user_id, role_id):
        """
        Assign role to user in project
        
        Args:
            project_id: Project ID
            user_id: User ID
            role_id: Role ID
        
        Returns:
            Tuple[bool, str]: (success, None) or (False, error_message)
        """
        try:
            if not self.admin_token:
                success, result = self.get_admin_token()
                if not success:
                    return False, f"Cannot get admin token: {result}"
            
            url = f"{self.keystone_url}/v3/projects/{project_id}/users/{user_id}/roles/{role_id}"
            headers = {"X-Auth-Token": self.admin_token}
            
            response = requests.put(url, headers=headers, timeout=10)
            
            if response.status_code in [201, 204]:
                logger.info(f"Role assigned: user={user_id}, project={project_id}, role={role_id}")
                return True, None
            elif response.status_code == 409:
                # Role already assigned
                logger.info(f"Role already assigned: user={user_id}, project={project_id}")
                return True, None
            else:
                error_msg = f"Role assignment failed: HTTP {response.status_code} - {response.text}"
                logger.error(error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Role assignment error: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    def provision_tenant(self, username, local_password, description=""):
        """
        Complete tenant provisioning pipeline
        
        Steps:
        1. Create project (tenant_<username>)
        2. Create user with auto-generated OpenStack password
        3. Get member role ID
        4. Assign member role to user in project
        
        Args:
            username: Local system username
            local_password: Local system password (NOT used for OpenStack)
            description: User/project description
        
        Returns:
            Tuple[bool, dict]: (success, {project_id, user_id, openstack_password}) or (False, error_message)
        """
        try:
            logger.info(f"Starting tenant provisioning for user '{username}'")
            
            # Step 1: Create project
            project_name = f"tenant_{username}"
            success, result = self.create_project(project_name, description)
            if not success:
                return False, f"Project creation failed: {result}"
            project_id = result
            
            # Step 2: Create user with auto-generated OpenStack password
            success, result = self.create_user(username, description=description)
            if not success:
                return False, f"User creation failed: {result}"
            user_id = result['user_id']
            openstack_password = result['password']
            
            # Step 3: Get member role ID
            success, result = self.get_role_id("member")
            if not success:
                return False, f"Role lookup failed: {result}"
            role_id = result
            
            # Step 4: Assign member role
            success, result = self.assign_role(project_id, user_id, role_id)
            if not success:
                return False, f"Role assignment failed: {result}"
            
            logger.info(f"Tenant provisioning completed for '{username}': project={project_id}, user={user_id}")
            
            return True, {
                "project_id": project_id,
                "project_name": project_name,
                "user_id": user_id,
                "openstack_password": openstack_password
            }
            
        except Exception as e:
            error_msg = f"Tenant provisioning error: {e}"
            logger.error(error_msg)
            return False, error_msg
