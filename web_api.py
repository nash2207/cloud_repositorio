"""FastAPI Web Interface for Slice Manager"""
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import hashlib
import uvicorn
import os

from database import Database
from remote_executor import RemoteExecutor
from deployment_api import DeploymentAPI
from orchestrator_api import OrchestratorAPI
from sync_manager import SyncManager
from vnc_proxy import vnc_proxy_manager

# Initialize FastAPI
app = FastAPI(title="Slice Manager API")
templates = Jinja2Templates(directory="templates")

# Mount noVNC static files if directory exists
if os.path.exists("static/novnc"):
    app.mount("/novnc", StaticFiles(directory="static/novnc"), name="novnc")

# Initialize backend components
db = Database()
executor = RemoteExecutor()
deployment = DeploymentAPI(executor)
orchestrator = OrchestratorAPI(db, deployment)
sync_manager = SyncManager(db, executor)

# Simple session storage (in production use Redis/JWT)
sessions = {}

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
    
    success, result = orchestrator.create_slice(user, slice_req.name, "custom", slice_req.availability_zone)
    if not success:
        raise HTTPException(status_code=400, detail=result)
    
    return result

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

@app.post("/api/slices/{slice_id}/deploy")
async def api_deploy_slice(slice_id: int, request: Request):
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    slice_data = db.get_slice(str(slice_id))
    if not slice_data:
        raise HTTPException(status_code=404, detail="Slice not found")
    
    if slice_data.get("owner") != user:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Set status to provisioning
    slice_data["status"] = "provisioning"
    db.update_slice(slice_id, slice_data)
    
    # Deploy synchronously (in production use background tasks)
    success, msg = orchestrator.deploy_slice(user, slice_id)
    
    if not success:
        # Revert to design on failure
        slice_data["status"] = "design"
        db.update_slice(slice_id, slice_data)
        raise HTTPException(status_code=400, detail=msg)
    
    return {"success": True, "message": msg}

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
    user = verify_session(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
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
        raise HTTPException(status_code=404, detail="VM not found or not authorized")
    
    # Check if VM is deployed
    if vm_found.get("status") != "deployed":
        raise HTTPException(status_code=400, detail="VM is not deployed")
    
    vnc_port = vm_found.get("vnc_port")
    worker_ip = vm_found.get("worker_ip")
    
    if not vnc_port or not worker_ip:
        raise HTTPException(status_code=400, detail="VM VNC information not available")
    
    # Get or create websockify proxy
    proxy_port = vnc_proxy_manager.get_proxy_port(worker_ip, vnc_port)
    
    if not proxy_port:
        raise HTTPException(status_code=500, detail="Failed to create VNC proxy")
    
    # Return noVNC URL pointing to websockify proxy
    # Format: http://localhost:8080/novnc/vnc.html?host=localhost&port=PROXY_PORT
    return {
        "vm_id": vm_id,
        "vm_name": vm_found.get("name"),
        "vnc_port": vnc_port,
        "worker_ip": worker_ip,
        "proxy_port": proxy_port,
        "console_url": f"/novnc/vnc.html?host=localhost&port={proxy_port}&autoconnect=true&resize=scale"
    }
