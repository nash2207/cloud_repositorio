"""FastAPI Web Interface for Slice Manager"""
from fastapi import FastAPI, Request, HTTPException, Response, WebSocket
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import hashlib
import uvicorn
import os
import asyncio
import time
import logging
from pathlib import Path

from database import Database
from remote_executor import RemoteExecutor
from deployment_api import DeploymentAPI
from orchestrator_api import OrchestratorAPI
from sync_manager import SyncManager
from vnc_proxy import vnc_proxy_manager
from monitoring.monitor import MonitoringSystem
from vm_placement import VMPlacementGA

logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(title="Slice Manager API")
templates = Jinja2Templates(directory="templates")

# Initialize backend components
db = Database()
executor = RemoteExecutor()
deployment = DeploymentAPI(executor, database=db)

# Initialize monitoring system
clusters = db.data.get("clusters", {
    "linux": {
        "bind_address": "10.0.0.6",
        "network_node": "10.0.0.1",
        "workers": ["10.0.0.2", "10.0.0.3", "10.0.0.4"]
    }
})

# Only include enabled clusters (OpenStack commented out in database.yaml)
# Global state (will be set by main.py when starting web mode)
monitoring_system = None
orchestrator = None  # Will be initialized after monitoring_system is set

def set_monitoring_system(ms):
    """Set the monitoring system instance from main.py"""
    global monitoring_system, orchestrator
    monitoring_system = ms
    
    # Initialize orchestrator with injected providers (Hexagonal Architecture)
    if not orchestrator:
        from providers.baremetal_provider import BareMetalComputeProvider
        from providers.ovs_network_provider import OVSNetworkProvider
        from providers.openstack_compute_provider import OpenStackComputeProvider
        from providers.neutron_network_provider import NeutronNetworkProvider
        from vlan_trunk_manager import VLANTrunkManager
        
        # Provider factory: decides which concrete implementations to use
        clusters_config = db.data.get("clusters", {})
        linux_cluster = clusters_config.get("linux", {})
        
        # Linux cluster providers (default)
        compute_provider = BareMetalComputeProvider(executor)
        network_provider = OVSNetworkProvider(
            executor,
            network_node_ip=linux_cluster.get("network_node", "10.0.0.1"),
            bridge_name="br-provider"
        )
        vlan_manager = VLANTrunkManager(executor, "10.0.0.7")
        
        # Inject dependencies into orchestrator (follows Dependency Injection pattern)
        # Note: Current design uses single provider pair. For multi-cluster support,
        # orchestrator would need provider registry indexed by availability_zone
        orchestrator = OrchestratorAPI(
            db, 
            deployment, 
            monitoring_system,
            compute_provider=compute_provider,      # ← Injected (Linux default)
            network_provider=network_provider,      # ← Injected (Linux default)
            vlan_trunk_manager=vlan_manager,        # ← Injected
            clusters_config=clusters_config
        )
        
        logger.info("Orchestrator initialized with Linux providers (Hexagonal Architecture)")
    
    # Re-initialize orchestrator with monitoring system (uses same injected providers)
    if orchestrator:
        orchestrator.monitoring_system = ms
        
        # Reinitialize GA with new monitoring system
        if "linux" in orchestrator.clusters:
            orchestrator.linux_placement_ga = VMPlacementGA(
                ms,
                orchestrator.clusters["linux"],
                "linux"
            )
            logger.info("VM Placement GA reinitialized with monitoring system")
sync_manager = SyncManager(db, executor)

# Simple session storage (in production use Redis/JWT)
sessions = {}

# ============= WebSocket Endpoint (BEFORE static mount) =============
@app.websocket("/vnc_ws/{proxy_port}")
async def vnc_websocket_proxy(websocket: WebSocket, proxy_port: int):
    """WebSocket proxy to websockify - allows VNC through same port as web app"""
    import websockets
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"WebSocket connection attempt for proxy port {proxy_port}")
    await websocket.accept()
    logger.info(f"WebSocket connection accepted for proxy port {proxy_port}")
    
    try:
        # Connect to local websockify
        ws_url = f"ws://localhost:{proxy_port}"
        logger.info(f"Attempting to connect to websockify at {ws_url}")
        
        async with websockets.connect(ws_url) as ws:
            logger.info(f"Successfully connected to websockify at localhost:{proxy_port}")
            
            # Bidirectional relay between browser and websockify
            async def relay_client_to_server():
                try:
                    while True:
                        data = await websocket.receive_bytes()
                        await ws.send(data)
                except Exception as e:
                    logger.info(f"Client->Server relay ended: {type(e).__name__}: {e}")
                    raise
            
            async def relay_server_to_client():
                try:
                    async for message in ws:
                        if isinstance(message, bytes):
                            await websocket.send_bytes(message)
                        else:
                            await websocket.send_text(message)
                except Exception as e:
                    logger.info(f"Server->Client relay ended: {type(e).__name__}: {e}")
                    raise
            
            # Run both relay tasks
            await asyncio.gather(
                relay_client_to_server(),
                relay_server_to_client(),
                return_exceptions=True
            )
    except asyncio.CancelledError:
        # Graceful shutdown - don't log error
        pass
    except websockets.exceptions.WebSocketException as e:
        logger.error(f"WebSocket error connecting to websockify at localhost:{proxy_port}: {e}")
        await websocket.close(code=1011, reason=f"Cannot connect to VNC proxy: {e}")
    except ConnectionRefusedError as e:
        logger.error(f"Connection refused to websockify at localhost:{proxy_port}: {e}")
        await websocket.close(code=1011, reason="VNC proxy not available")
    except Exception as e:
        logger.error(f"WebSocket proxy error for port {proxy_port}: {type(e).__name__}: {e}")
        await websocket.close(code=1011, reason=f"Proxy error: {e}")
    finally:
        logger.info(f"WebSocket closed for proxy port {proxy_port}")

# ============= Static Files (AFTER WebSocket routes) =============
# Serve noVNC files manually to avoid WebSocket capture
@app.get("/novnc/{file_path:path}")
async def serve_novnc(file_path: str):
    """Serve noVNC static files"""
    novnc_dir = Path("static/novnc")
    file_full_path = novnc_dir / file_path
    
    if file_full_path.exists() and file_full_path.is_file():
        return FileResponse(file_full_path)
    else:
        raise HTTPException(status_code=404, detail="File not found")

# ============= Authentication =============
def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def verify_session(request: Request):
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in sessions:
        return None
    return sessions[session_id]

# ============= Models =============
class LoginRequest(BaseModel):
    username: str
    password: str

class CreateSliceRequest(BaseModel):
    name: str
    availability_zone: str = "linux"  # Default to linux cluster

class AddVMRequest(BaseModel):
    slice_id: int
    vm_name: str
    flavor: str
    internet_enabled: bool

class CreateLinkRequest(BaseModel):
    slice_id: int
    vm1_id: int
    vm2_id: int

class UpdateVMRequest(BaseModel):
    vm_name: str = None
    flavor: str = None
    internet_enabled: bool = None

class TopologyPresetRequest(BaseModel):
    topology_type: str  # ring, bus, star, mesh
    num_vms: int
    flavor: str = "cirros"
    internet: bool = False
    base_name: str = "vm"

# ============= HTML Routes =============
@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse(url="/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    user = verify_session(request)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("dashboard.html", {"request": request, "username": user})

@app.get("/monitoring", response_class=HTMLResponse)
async def monitoring_page(request: Request):
    """Monitoring dashboard (admin only)"""
    user = verify_session(request)
    if not user:
        return RedirectResponse(url="/login")
    
    # Check if user is admin
    user_data = db.get_user(user)
    if user_data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return templates.TemplateResponse("monitoring.html", {"request": request, "username": user})

# ============= API Routes =============
@app.post("/api/login")
async def api_login(login: LoginRequest, response: Response):
    user = db.get_user(login.username)
    if user and user.get("password_hash") == hash_password(login.password):
        session_id = hashlib.sha256(f"{login.username}{hash(login.password)}".encode()).hexdigest()
        sessions[session_id] = login.username
        response.set_cookie(key="session_id", value=session_id, httponly=True)
        return {"success": True, "username": login.username}
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/api/logout")
async def api_logout(request: Request, response: Response):
    session_id = request.cookies.get("session_id")
    if session_id in sessions:
        del sessions[session_id]
    response.delete_cookie("session_id")
    return {"success": True}

# ============= User Management (Admin Only) =============
class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "student"
    quota_vms: int = 10

@app.get("/api/users")
async def api_get_users(request: Request):
    """Get all users (admin only)"""
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_data = db.get_user(user)
    if user_data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Return all users except admin
    users = []
    for username, data in db.data.get("users", {}).items():
        if username != "admin":
            users.append({
                "username": username,
                "role": data.get("role", "student"),
                "quota_vms": data.get("quota_vms", 10),
                "used_vms": data.get("used_vms", 0),
                "slices": len(data.get("slices", [])),
                "openstack_provisioned": "openstack" in data
            })
    
    return {"users": users}

@app.post("/api/users")
async def api_create_user(user_req: CreateUserRequest, request: Request):
    """Create new user with OpenStack provisioning (admin only)"""
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_data = db.get_user(user)
    if user_data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Import user provisioning service
    from user_provisioning import provision_user_with_openstack
    from audit_log import log_admin_action
    
    # Create user with OpenStack integration
    success, result = provision_user_with_openstack(
        db, 
        user_req.username, 
        user_req.password, 
        user_req.role, 
        user_req.quota_vms
    )
    
    if success:
        log_admin_action(
            user, 
            f"Created user '{user_req.username}'", 
            {
                "new_user": user_req.username,
                "role": user_req.role,
                "quota_vms": user_req.quota_vms,
                "openstack_provisioned": "openstack" in result
            }
        )
        return {
            "success": True, 
            "username": user_req.username,
            "openstack_provisioned": "openstack" in result
        }
    else:
        log_admin_action(
            user, 
            f"Failed to create user '{user_req.username}'", 
            {"error": result},
            level="ERROR"
        )
        raise HTTPException(status_code=400, detail=result)

@app.delete("/api/users/{username}")
async def api_delete_user(username: str, request: Request):
    """Delete user (admin only) - syncs with OpenStack"""
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_data = db.get_user(user)
    if user_data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    if username == "admin":
        raise HTTPException(status_code=400, detail="Cannot delete admin user")
    
    target_user = db.get_user(username)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    from audit_log import log_admin_action
    
    logger.info(f"Deleting user {username} - syncing with OpenStack")
    
    # Delete all slices first
    for slice_id in target_user.get("slices", []):
        orchestrator.delete_slice(username, slice_id)
    
    # Delete from OpenStack if provisioned
    if "openstack" in target_user:
        try:
            from openstack.keystone_client import KeystoneClient
            
            openstack_config = db.data.get("openstack", {})
            keystone = KeystoneClient(
                auth_url=openstack_config.get("keystone_url"),
                admin_username=openstack_config.get("admin_username"),
                admin_password=openstack_config.get("admin_password"),
                admin_project=openstack_config.get("admin_project", "admin")
            )
            
            openstack_data = target_user["openstack"]
            project_id = openstack_data.get("project_id")
            user_id = openstack_data.get("user_id")
            
            # Delete OpenStack user
            if user_id:
                keystone.delete_user(user_id)
                logger.info(f"Deleted OpenStack user {user_id} for {username}")
            
            # Delete OpenStack project
            if project_id:
                keystone.delete_project(project_id)
                logger.info(f"Deleted OpenStack project {project_id} for {username}")
            
        except Exception as e:
            logger.error(f"Error deleting from OpenStack: {e}")
            # Continue with local deletion even if OpenStack fails
    
    # Delete user from local database
    with db.lock:
        del db.data["users"][username]
        db.save()
    
    log_admin_action(
        user,
        f"Deleted user '{username}'",
        {
            "deleted_user": username,
            "slices_deleted": len(target_user.get("slices", [])),
            "openstack_cleanup": "openstack" in target_user
        }
    )
    
    logger.info(f"User {username} deleted successfully")
    return {"success": True, "message": f"User {username} deleted"}

# ============= Quota Management =============

@app.get("/api/quotas")
async def api_quotas(request: Request):
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_data = db.get_user(user)
    return {
        "used_vms": user_data.get("used_vms", 0),
        "quota_vms": user_data.get("quota_vms", 10),
        "slices": len(user_data.get("slices", [])),
        "vlan_pool": "200-219"
    }

@app.get("/api/slices")
async def api_get_slices(request: Request):
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_data = db.get_user(user)
    slice_ids = user_data.get("slices", [])
    slices = []
    
    for slice_id in slice_ids:
        slice_data = db.get_slice(slice_id)
        if slice_data:
            slices.append({
                "slice_id": slice_data.get("slice_id"),
                "status": slice_data.get("status", "design"),
                "availability_zone": slice_data.get("availability_zone", "linux"),
                "vms": slice_data.get("vms", []),
                "links": slice_data.get("links", []),
                "vlan_pool_start": slice_data.get("vlan_pool_start"),
                "vlan_pool_end": slice_data.get("vlan_pool_end")
            })
    
    return {"slices": slices}

@app.get("/api/slices/{slice_id}")
async def api_get_slice(slice_id: int, request: Request):
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    slice_data = db.get_slice(str(slice_id))
    if not slice_data or slice_data.get("owner") != user:
        raise HTTPException(status_code=404, detail="Slice not found")
    
    return slice_data

@app.post("/api/slices")
async def api_create_slice(slice_req: CreateSliceRequest, request: Request):
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Validate availability zone
    if slice_req.availability_zone not in ["linux", "openstack"]:
        raise HTTPException(status_code=400, detail="Invalid availability_zone. Choose 'linux' or 'openstack'")
    
    # Register OpenStack providers on-demand if needed
    if slice_req.availability_zone == "openstack" and orchestrator:
        _ensure_openstack_providers_registered()
    
    success, result = orchestrator.create_slice(user, slice_req.name, "custom", slice_req.availability_zone)
    if not success:
        raise HTTPException(status_code=400, detail=result)
    
    return result

def _ensure_openstack_providers_registered():
    """Lazily register OpenStack providers when first needed"""
    if "openstack" in orchestrator._provider_registry:
        return  # Already registered
    
    try:
        from providers.openstack_compute_provider import OpenStackComputeProvider
        from providers.neutron_network_provider import NeutronNetworkProvider
        from openstack.connection import create_admin_connection
        
        # Get OpenStack configuration
        openstack_config = db.data.get("openstack", {})
        
        if not openstack_config.get("enabled", False):
            logger.warning("OpenStack providers requested but OpenStack is disabled in config")
            return
        
        # Create OpenStack connection
        connection = create_admin_connection(
            auth_url=openstack_config.get("keystone_url", "http://10.60.8.1:5000/v3"),
            admin_username=openstack_config.get("admin_user", "admin"),
            admin_password=openstack_config.get("admin_password"),
            admin_project="admin"
        )
        
        # Create providers
        openstack_compute = OpenStackComputeProvider(connection)
        openstack_network = NeutronNetworkProvider(connection)
        
        # Register with orchestrator
        orchestrator.register_providers("openstack", openstack_compute, openstack_network)
        
        logger.info("OpenStack providers registered successfully")
        
    except Exception as e:
        logger.error(f"Failed to register OpenStack providers: {e}")
        raise HTTPException(status_code=503, detail=f"OpenStack initialization failed: {e}")

@app.post("/api/slices/{slice_id}/vms")
async def api_add_vm(slice_id: int, vm_req: AddVMRequest, request: Request):
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    success, result = orchestrator.add_vm_to_slice(
        user, slice_id, vm_req.vm_name, vm_req.flavor, vm_req.internet_enabled
    )
    if not success:
        raise HTTPException(status_code=400, detail=result)
    
    return result

@app.post("/api/slices/{slice_id}/links")
async def api_create_link(slice_id: int, link_req: CreateLinkRequest, request: Request):
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    success, result = orchestrator.create_link(
        user, slice_id, link_req.vm1_id, link_req.vm2_id
    )
    if not success:
        raise HTTPException(status_code=400, detail=result)
    
    return result

@app.delete("/api/slices/{slice_id}/links/{link_id}")
async def api_delete_link(slice_id: int, link_id: int, request: Request):
    """Delete a link between two VMs (works in both design and deployed states)"""
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    success, result = orchestrator.delete_link(user, slice_id, link_id)
    if not success:
        raise HTTPException(status_code=400, detail=result)
    
    return result

@app.post("/api/slices/{slice_id}/deploy")
async def api_deploy_slice(slice_id: int, request: Request):
    """Deploy slice asynchronously with progress updates"""
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    slice_data = db.get_slice(str(slice_id))
    if not slice_data:
        raise HTTPException(status_code=404, detail="Slice not found")
    
    if slice_data.get("owner") != user:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Set status to provisioning immediately
    slice_data["status"] = "provisioning"
    db.update_slice(slice_id, slice_data)
    
    # Return immediately - deployment happens in background
    # Frontend will poll /api/slices/{slice_id} for status updates
    logger.info(f"Starting async deployment of slice {slice_id}")
    
    # Deploy in background thread (FastAPI will handle it)
    import threading
    def deploy_background():
        try:
            success, msg = orchestrator.deploy_slice(user, slice_id)
            if not success:
                # Revert to design on failure
                slice_data_updated = db.get_slice(str(slice_id))
                slice_data_updated["status"] = "design"
                slice_data_updated["deploy_error"] = msg
                db.update_slice(slice_id, slice_data_updated)
                logger.error(f"Deployment failed for slice {slice_id}: {msg}")
        except Exception as e:
            logger.error(f"Deployment exception for slice {slice_id}: {e}")
            slice_data_updated = db.get_slice(str(slice_id))
            slice_data_updated["status"] = "design"
            slice_data_updated["deploy_error"] = str(e)
            db.update_slice(slice_id, slice_data_updated)
    
    threading.Thread(target=deploy_background, daemon=True).start()
    
    return {"success": True, "message": "Deployment started", "status": "provisioning"}

@app.post("/api/slices/{slice_id}/deploy-edition")
async def api_deploy_edition(slice_id: int, request: Request):
    """Deploy only pending VMs in an already deployed slice (Deploy Edition)"""
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    slice_data = db.get_slice(str(slice_id))
    if not slice_data:
        raise HTTPException(status_code=404, detail="Slice not found")
    
    if slice_data.get("owner") != user:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if slice_data.get("status") != "deployed":
        raise HTTPException(status_code=400, detail="Slice must be deployed to use Deploy Edition")
    
    logger.info(f"Starting Deploy Edition for slice {slice_id}")
    
    # Deploy pending VMs in background
    import threading
    def deploy_edition_background():
        try:
            success, msg = orchestrator.deploy_slice_edition(user, slice_id)
            if not success:
                logger.error(f"Deploy Edition failed for slice {slice_id}: {msg}")
        except Exception as e:
            logger.error(f"Deploy Edition exception for slice {slice_id}: {e}")
    
    threading.Thread(target=deploy_edition_background, daemon=True).start()
    
    return {"success": True, "message": "Deploy Edition started"}

@app.delete("/api/slices/{slice_id}")
async def api_delete_slice(slice_id: int, request: Request):
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    success, msg = orchestrator.delete_slice(user, slice_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    
    return {"success": True, "message": msg}

@app.post("/api/cleanup-orphaned")
async def api_cleanup_orphaned(request: Request):
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    sync_manager.cleanup_orphaned_vms()
    return {"success": True, "message": "Orphaned VMs cleaned up"}

@app.patch("/api/slices/{slice_id}/vms/{vm_id}")
async def api_update_vm(slice_id: int, vm_id: int, vm_req: UpdateVMRequest, request: Request):
    """Update VM properties (only in design state)"""
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    success, result = orchestrator.update_vm(user, slice_id, vm_id, vm_req.dict(exclude_none=True))
    if not success:
        raise HTTPException(status_code=400, detail=result)
    
    return result

@app.post("/api/slices/{slice_id}/topology")
async def api_create_topology(slice_id: int, topo_req: TopologyPresetRequest, request: Request):
    """Create predefined topology"""
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    success, result = orchestrator.create_topology_preset(
        user, slice_id, topo_req.topology_type, topo_req.num_vms,
        topo_req.flavor, topo_req.internet, topo_req.base_name
    )
    if not success:
        raise HTTPException(status_code=400, detail=result)
    
    return result

@app.get("/api/slices/{slice_id}/export")
async def api_export_slice(slice_id: int, request: Request):
    """Export slice to JSON"""
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    success, result = orchestrator.export_slice_json(user, slice_id)
    if not success:
        raise HTTPException(status_code=400, detail=result)
    
    return JSONResponse(content=result)

@app.post("/api/slices/import")
async def api_import_slice(request: Request):
    """Import slice from JSON"""
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    data = await request.json()
    success, result = orchestrator.import_slice_json(user, data)
    if not success:
        raise HTTPException(status_code=400, detail=result)
    
    return result

@app.get("/api/vms/{vm_id}/console")
async def api_get_vm_console(vm_id: int, request: Request):
    """Get noVNC console URL for VM"""
    import logging
    logger = logging.getLogger(__name__)
    
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    logger.info(f"Console request for VM {vm_id} by user {user}")
    
    # Find VM in user's slices
    user_data = db.get_user(user)
    slice_ids = user_data.get("slices", [])
    
    vm_found = None
    for slice_id in slice_ids:
        slice_data = db.get_slice(slice_id)
        if slice_data:
            for vm in slice_data.get("vms", []):
                if vm["vm_id"] == vm_id:
                    vm_found = vm
                    break
        if vm_found:
            break
    
    if not vm_found:
        logger.error(f"VM {vm_id} not found")
        raise HTTPException(status_code=404, detail="VM not found or not authorized")
    
    # Check if VM is deployed
    if vm_found.get("status") != "deployed":
        logger.error(f"VM {vm_id} not deployed, status: {vm_found.get('status')}")
        raise HTTPException(status_code=400, detail="VM is not deployed")
    
    vnc_port = vm_found.get("vnc_port")
    worker_ip = vm_found.get("worker_ip")
    
    logger.info(f"VM {vm_id} details: worker={worker_ip}, vnc_port={vnc_port}")
    
    if not vnc_port or not worker_ip:
        raise HTTPException(status_code=400, detail="VM VNC information not available")
    
    # Get or create websockify proxy
    logger.info(f"Requesting proxy for {worker_ip}:{vnc_port}")
    proxy_port = vnc_proxy_manager.get_proxy_port(worker_ip, vnc_port)
    
    if not proxy_port:
        logger.error(f"Failed to create proxy for {worker_ip}:{vnc_port}")
        raise HTTPException(status_code=500, detail="Failed to create VNC proxy")
    
    logger.info(f"Proxy created: localhost:{proxy_port} -> {worker_ip}:{vnc_port}")
    
    # Return noVNC URL using WebSocket proxy through FastAPI
    # This way everything goes through port 8080 (works with SSH tunnel)
    # Note: path should be relative to the page location (already at /novnc/)
    console_url = f"/novnc/vnc.html?path=../vnc_ws/{proxy_port}&autoconnect=true&resize=scale"
    
    logger.info(f"Returning console URL: {console_url}")
    
    return {
        "vm_id": vm_id,
        "vm_name": vm_found.get("name"),
        "vnc_port": vnc_port,
        "worker_ip": worker_ip,
        "proxy_port": proxy_port,
        "console_url": console_url
    }


# ============= Monitoring API Endpoints =============
@app.get("/api/monitoring/workers")
async def api_get_workers_stats(request: Request):
    """Get statistics for all workers (admin only)"""
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Check if user is admin
    user_data = db.get_user(user)
    if user_data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Get all workers stats from monitoring system
    workers_stats = monitoring_system.get_all_workers_stats()
    
    return {
        "workers": workers_stats,
        "timestamp": time.time()
    }

@app.get("/api/monitoring/vms")
async def api_get_vms_stats(request: Request):
    """Get statistics for all VMs (admin only)"""
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Check if user is admin
    user_data = db.get_user(user)
    if user_data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Get all VMs stats from monitoring system
    vms_stats = monitoring_system.get_all_vms_stats()
    
    return {
        "vms": vms_stats,
        "timestamp": time.time()
    }

@app.get("/api/monitoring/cluster/{availability_zone}")
async def api_get_cluster_stats(availability_zone: str, request: Request):
    """Get aggregated statistics for a cluster (admin only)"""
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Check if user is admin
    user_data = db.get_user(user)
    if user_data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    if availability_zone not in ["linux", "openstack"]:
        raise HTTPException(status_code=400, detail="Invalid availability_zone")
    
    # Check if monitoring_system is available
    if not monitoring_system:
        logger.error("Monitoring system is None in API endpoint!")
        raise HTTPException(status_code=503, detail="Monitoring system not initialized")
    
    # Get cluster stats
    try:
        cluster_stats = monitoring_system.get_cluster_stats(availability_zone)
        logger.info(f"Cluster stats for {availability_zone}: {len(cluster_stats.get('workers', []))} workers, {cluster_stats.get('vms_count', 0)} VMs")
    except Exception as e:
        logger.error(f"Error getting cluster stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    return cluster_stats

@app.get("/api/openstack/resources")
async def api_get_openstack_resources(request: Request):
    """Get available OpenStack images and flavors (for admin debugging)"""
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_data = db.get_user(user)
    if user_data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Create OpenStack connection
        from openstack.connection import create_admin_connection
        from openstack.resource_mapper import OpenStackResourceMapper
        
        openstack_config = db.data.get("openstack", {})
        
        connection = create_admin_connection(
            auth_url=openstack_config.get("keystone_url", "http://10.60.8.1:5000/v3"),
            admin_username=openstack_config.get("admin_user", "admin"),
            admin_password=openstack_config.get("admin_password"),
            admin_project="admin"
        )
        
        mapper = OpenStackResourceMapper(connection)
        
        images = mapper.list_images()
        flavors = mapper.list_flavors()
        
        return {
            "images": images,
            "flavors": flavors
        }
        
    except Exception as e:
        logger.error(f"Failed to get OpenStack resources: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/images")
async def api_add_image(request: Request):
    """Add a new image to the system (admin only)"""
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_data = db.get_user(user)
    if user_data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        data = await request.json()
        image_name = data.get("name", "").strip()
        image_path = data.get("path", "").strip()
        
        if not image_name or not image_path:
            raise HTTPException(status_code=400, detail="Image name and path are required")
        
        # Add to models.Flavor
        from models import Flavor
        
        if image_name in Flavor.FLAVORS:
            raise HTTPException(status_code=400, detail=f"Image '{image_name}' already exists")
        
        # Add new flavor entry
        Flavor.FLAVORS[image_name] = {
            "cores": 1,
            "ram_gb": 0.5,
            "disk_gb": 2.5,
            "image": image_path,
            "interface_prefix": "ens"
        }
        
        logger.info(f"Admin {user} added new image: {image_name} -> {image_path}")
        
        return {
            "success": True,
            "message": f"Image '{image_name}' added successfully",
            "image": {
                "name": image_name,
                "path": image_path
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add image: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/images")
async def api_list_images(request: Request):
    """List all available images"""
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    from models import Flavor
    
    images = []
    for name, spec in Flavor.FLAVORS.items():
        images.append({
            "name": name,
            "path": spec.get("image"),
            "cores": spec.get("cores"),
            "ram_gb": spec.get("ram_gb"),
            "disk_gb": spec.get("disk_gb")
        })
    
    return {"images": images}

# ============= Audit Logs API =============
@app.get("/api/audit/logs")
async def api_get_audit_logs(request: Request, limit: int = 100, event_type: str = None):
    """Get audit logs (admin only)"""
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_data = db.get_user(user)
    if user_data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    from audit_log import audit_logger
    
    logs = audit_logger.get_logs(limit=limit, event_type=event_type)
    summary = audit_logger.get_logs_summary()
    
    return {
        "logs": logs,
        "summary": summary
    }

@app.get("/api/monitoring/vm/{vm_id}")
async def api_get_vm_stats(vm_id: int, request: Request):
    """Get statistics for a specific VM"""
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Check if user owns this VM
    user_data = db.get_user(user)
    is_admin = user_data.get("role") == "admin"
    
    # Find VM in user's slices (or any slice if admin)
    vm_found = False
    if is_admin:
        vm_found = True
    else:
        slice_ids = user_data.get("slices", [])
        for slice_id in slice_ids:
            slice_data = db.get_slice(slice_id)
            if slice_data:
                for vm in slice_data.get("vms", []):
                    if vm["vm_id"] == vm_id:
                        vm_found = True
                        break
            if vm_found:
                break
    
    if not vm_found:
        raise HTTPException(status_code=404, detail="VM not found or not authorized")
    
    # Get VM stats from monitoring system
    vm_stats = monitoring_system.get_vm_stats(vm_id)
    
    if not vm_stats:
        raise HTTPException(status_code=404, detail="VM stats not available yet")
    
    return {
        "vm": vm_stats,
        "timestamp": time.time()
    }
