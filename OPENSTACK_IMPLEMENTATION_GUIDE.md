# OpenStack Multi-Cluster Implementation Guide

## 🎯 Overview

This document describes the multi-cluster architecture with availability zones and provides guidance for completing the OpenStack provider implementation.

## 📐 Architecture

### Current Status: ✅ LINUX CLUSTER WORKING | ⚠️ OPENSTACK STUB READY

### Network Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                        APP NODE (Project)                        │
│  - ens4: 10.0.0.6  → Linux Cluster                              │
│  - ens5: 10.0.1.6  → OpenStack Cluster                          │
│  - SSH bind address per cluster for multi-NIC routing           │
└─────────────────────────────────────────────────────────────────┘
                │                            │
                │                            │
      ┌─────────▼─────────┐        ┌────────▼─────────┐
      │  LINUX CLUSTER    │        │ OPENSTACK CLUSTER│
      │  (AZ: "linux")    │        │  (AZ: "openstack")│
      └───────────────────┘        └──────────────────┘
              │                              │
    ┌─────────┼─────────┐          ┌────────┼─────────┐
    │         │         │          │        │         │
Network   Worker1  Worker2    HeadNode  Worker1  Worker2
10.0.0.1  10.0.0.2 10.0.0.3   10.0.1.1  10.0.1.2 10.0.1.3
          10.0.0.4                       10.0.1.4
```

### Cluster Details

#### Linux Cluster (WORKING ✅)
- **Availability Zone**: `linux`
- **Bind Address**: `10.0.0.6` (ens4)
- **Network Node**: `10.0.0.1` (OVS bridge, VLAN management)
- **Workers**: `10.0.0.2`, `10.0.0.3`, `10.0.0.4`
- **Technology**: Bare-metal QEMU/KVM with OVS networking
- **Provider**: `providers/baremetal_provider.py`

#### OpenStack Cluster (STUB ⚠️)
- **Availability Zone**: `openstack`
- **Bind Address**: `10.0.1.6` (ens5)
- **HeadNode**: `10.0.1.1` (Keystone, Nova, Neutron, Glance APIs)
- **Workers**: `10.0.1.2`, `10.0.1.3`, `10.0.1.4`
- **Technology**: OpenStack native REST APIs (NO SDK)
- **Provider**: `providers/openstack_provider.py` (STUB)

### API Endpoints (OpenStack HeadNode)

| Service  | Port | Purpose                          |
|----------|------|----------------------------------|
| Keystone | 5000 | Authentication & Multi-tenancy   |
| Nova     | 8774 | Instance management              |
| Neutron  | 9696 | Network/subnet/port management   |
| Glance   | 9292 | Image management                 |

## 🔧 Implementation Status

### ✅ COMPLETED

1. **Multi-Cluster Architecture**
   - `models.py`: Added `availability_zone` field to Slice model
   - `database.yaml`: Cluster configurations with bind addresses
   - `remote_executor.py`: Multi-NIC SSH support with bind_address

2. **Orchestrator Routing**
   - `orchestrator_api.py`: Provider selection based on AZ
   - `orchestrator_api.py`: Bind address configuration per cluster
   - `orchestrator_api.py`: Round-robin placement per cluster

3. **API Layer**
   - `web_api.py`: AZ parameter in create_slice endpoint
   - `web_api.py`: AZ validation (linux/openstack)

4. **UI Layer**
   - `templates/dashboard.html`: AZ selector in create slice modal
   - `templates/dashboard.html`: AZ indicators in slice list (🐧/☁️)
   - `templates/dashboard.html`: AZ display in topology header

5. **OpenStack Stub Structure**
   - `openstack/keystone_client.py`: Authentication flow (STUB)
   - `openstack/nova_client.py`: Instance management (STUB)
   - `openstack/neutron_client.py`: Network management (STUB)
   - `providers/openstack_provider.py`: Provider integration (STUB)

### ⚠️ TO BE COMPLETED

All OpenStack implementation is in **STUB** state. Search for `🚧 STUB` comments.

## 📋 OpenStack Implementation Checklist

### Phase 1: Authentication (keystone_client.py)

**File**: `openstack/keystone_client.py`

#### Tasks:
- [ ] Implement `get_admin_token()`
  - POST to `/v3/auth/tokens` with admin credentials
  - Capture `X-Subject-Token` from response header
  
- [ ] Implement `get_cloud_domain_id()`
  - GET `/v3/domains`
  - Filter for domain name="Cloud"
  - Return domain ID
  
- [ ] Implement `create_project(project_name, domain_id)`
  - POST `/v3/projects`
  - Use Cloud domain ID (NOT "default")
  
- [ ] Implement `create_user(username, password, domain_id)`
  - POST `/v3/users`
  - Use Cloud domain ID
  
- [ ] Implement `get_role_id(role_name="member")`
  - GET `/v3/roles?name=member`
  
- [ ] Implement `assign_role(project_id, user_id, role_id)`
  - PUT `/v3/projects/{project_id}/users/{user_id}/roles/{role_id}`
  
- [ ] Implement `get_scoped_token(username, password, project_id, domain_id)`
  - POST `/v3/auth/tokens` with scope
  - Return scoped token for Nova/Neutron operations

#### Example Authentication Flow:
```python
# 1. Admin auth
success, admin_token = keystone.get_admin_token("cloud_admin", "admin")

# 2. Get Cloud domain
success, domain_id = keystone.get_cloud_domain_id()

# 3. Create project for slice
success, project_id = keystone.create_project("slice_1000", domain_id)

# 4. Create user
success, user_id = keystone.create_user("student_slice1000", "password", domain_id)

# 5. Assign role
success, role_id = keystone.get_role_id("member")
keystone.assign_role(project_id, user_id, role_id)

# 6. Get scoped token for user
success, scoped_token = keystone.get_scoped_token("student_slice1000", "password", project_id, domain_id)
```

### Phase 2: Networking (neutron_client.py)

**File**: `openstack/neutron_client.py`

#### Tasks:
- [ ] Implement `create_network(token, project_id, network_name)`
  - POST `/v2.0/networks`
  - One network per Link in slice
  
- [ ] Implement `create_subnet(token, project_id, network_id, subnet_name, cidr)`
  - POST `/v2.0/subnets`
  - CIDR: `192.168.X.0/24` (where X = vlan_id % 256)
  
- [ ] Implement `create_port(token, project_id, network_id, port_name)`
  - POST `/v2.0/ports`
  - One port per VM interface
  - Returns port_id, mac_address, fixed_ips
  
- [ ] Implement cleanup methods
  - `delete_network(token, network_id)`
  - `delete_port(token, port_id)`
  - `list_ports(token, project_id)`

#### Example Network Flow:
```python
# For each Link in slice
link = {"link_id": 1, "vlan_id": 160}

# Create network
success, net_id = neutron.create_network(
    scoped_token, project_id, f"net_link{link['link_id']}_vlan{link['vlan_id']}"
)

# Create subnet
cidr = f"192.168.{link['vlan_id'] % 256}.0/24"
success, subnet_id = neutron.create_subnet(
    scoped_token, project_id, net_id, f"subnet_link{link['link_id']}", cidr
)

# Create ports for VMs
success, port1 = neutron.create_port(scoped_token, project_id, net_id, "port_vm1_eth1")
success, port2 = neutron.create_port(scoped_token, project_id, net_id, "port_vm2_eth1")
```

### Phase 3: Compute (nova_client.py)

**File**: `openstack/nova_client.py`

#### Tasks:
- [ ] Implement `create_instance(token, project_id, name, flavor_id, image_id, port_ids)`
  - POST `/v2.1/servers`
  - Attach all port_ids at boot
  
- [ ] Implement `wait_for_active(token, server_id)`
  - Poll GET `/v2.1/servers/{server_id}`
  - Wait until status=ACTIVE
  
- [ ] Implement `attach_interface(token, server_id, port_id)`
  - POST `/v2.1/servers/{server_id}/os-interface`
  - For hot-plug during topology editing
  
- [ ] Implement `soft_reboot(token, server_id)`
  - POST `/v2.1/servers/{server_id}/action`
  - Payload: `{"reboot": {"type": "SOFT"}}`
  - Required for Cirros to activate hot-plugged interfaces
  
- [ ] Implement `get_instance(token, server_id)`
  - GET `/v2.1/servers/{server_id}`
  
- [ ] Implement `delete_instance(token, server_id)`
  - DELETE `/v2.1/servers/{server_id}`

#### Example Instance Creation:
```python
# Get flavor and image IDs (may need discovery first)
flavor_id = "cirros-flavor-id"
image_id = "cirros-image-id"

# Collect port IDs for all interfaces
port_ids = [port1['port_id'], port2['port_id']]

# Create instance
success, result = nova.create_instance(
    scoped_token, project_id, "vm1", flavor_id, image_id, port_ids
)
server_id = result['server_id']

# Wait for ACTIVE
success, status = nova.wait_for_active(scoped_token, server_id)
```

### Phase 4: Provider Integration (openstack_provider.py)

**File**: `providers/openstack_provider.py`

#### Tasks:
- [ ] Implement `_authenticate_admin()`
  - Call KeystoneClient methods
  - Cache admin token
  
- [ ] Implement `_get_cloud_domain()`
  - Get and cache Cloud domain ID
  
- [ ] Implement `_setup_project(slice_id, slice_owner)`
  - Create project for slice
  - Create user for slice owner
  - Assign member role
  - Get scoped token
  - Cache project_id and token
  
- [ ] Implement `_create_network_for_link(token, project_id, link_dict)`
  - Create network and subnet via NeutronClient
  - Return network_id, subnet_id
  
- [ ] Implement `_create_port_for_interface(token, project_id, network_id, vm_name, iface_name)`
  - Create port via NeutronClient
  - Return port_id, mac_address, ip
  
- [ ] Implement `launch_vm(worker_ip, vm_dict)`
  - Get/create project setup
  - Map flavor_name to OpenStack flavor_id
  - Get image_id (Cirros/Ubuntu)
  - Create ports for all VM interfaces
  - Create Nova instance
  - Wait for ACTIVE
  - Return server_id
  
- [ ] Implement `stop_vm(worker_ip, vm_dict)`
  - Delete instance
  - Delete associated ports
  
- [ ] Implement `get_running_vms(worker_ip)`
  - List instances in project
  
- [ ] Implement `attach_interface_hotplug(slice_id, vm_id, port_id, is_cirros)`
  - Attach port to running instance
  - Soft reboot if Cirros

#### Example Full Deployment:
```python
# In orchestrator_api.py deploy_slice() for AZ=openstack
compute_provider = self.openstack_compute_provider

# For each link, create network
for link in slice_data['links']:
    network_id, subnet_id = compute_provider._create_network_for_link(
        scoped_token, project_id, link
    )

# For each VM, create ports then launch
for vm_dict in slice_data['vms']:
    port_ids = []
    for iface in vm_dict['interfaces']:
        port_id = compute_provider._create_port_for_interface(
            scoped_token, project_id, network_id, vm_dict['name'], iface['name']
        )
        port_ids.append(port_id)
    
    # Launch instance (worker_ip ignored - Nova scheduler handles placement)
    success, server_id = compute_provider.launch_vm(None, vm_dict)
```

## 🧪 Testing Strategy

### Phase 1: Test with Linux Cluster (Already Working)
```bash
# Start web API
python3 main.py

# Login as student/student
# Create slice with AZ="linux"
# Add VMs, create links, deploy
# Verify VMs launch on 10.0.0.x workers
```

### Phase 2: Test OpenStack Authentication
```python
# Test keystone_client.py methods independently
from openstack.keystone_client import KeystoneClient

keystone = KeystoneClient("http://10.0.1.1:5000")

# Test admin auth
success, token = keystone.get_admin_token("cloud_admin", "admin")
print(f"Admin token: {token[:20]}...")

# Test domain lookup
success, domain_id = keystone.get_cloud_domain_id()
print(f"Cloud domain ID: {domain_id}")
```

### Phase 3: Test Network Creation
```python
from openstack.neutron_client import NeutronClient

neutron = NeutronClient("http://10.0.1.1:9696")

# Create test network
success, net_id = neutron.create_network(scoped_token, project_id, "test_net")
print(f"Network ID: {net_id}")
```

### Phase 4: Test Instance Creation
```python
from openstack.nova_client import NovaClient

nova = NovaClient("http://10.0.1.1:8774")

# Create test instance
success, result = nova.create_instance(
    scoped_token, project_id, "test_vm", flavor_id, image_id, [port_id]
)
print(f"Server ID: {result['server_id']}")
```

### Phase 5: End-to-End Test
```bash
# Via UI:
# 1. Create slice with AZ="openstack"
# 2. Add 2 Cirros VMs
# 3. Create link between them
# 4. Deploy slice
# 5. Verify instances created in OpenStack
# 6. Check Neutron networks and ports
# 7. Test connectivity between VMs
```

## 🚨 Important Notes

### Authentication
- **Admin creates all projects and users** - normal users CANNOT create accounts
- Always use **Cloud domain ID** (not "default") for projects and users
- Scoped tokens required for Nova/Neutron/Glance operations
- Handle 401 errors (token expiration) by re-authenticating

### Hot-Plug (Incremental Topology Editing)
- **Cirros VMs**: Require soft reboot after interface hot-plug
  - Cirros lacks full dynamic udev support
  - After attaching port, trigger soft reboot (~2 seconds)
  - VM will re-read PCI bus and configure new interface via DHCP
  
- **Ubuntu VMs**: Handle hot-plug cleanly
  - Dynamic udev detects new interface automatically
  - No reboot required

### Networking
- Each **Link** → One Neutron network + subnet
- Each **VM interface** on that link → One Neutron port
- VLAN IDs map to CIDR: `192.168.{vlan_id % 256}.0/24`

### Error Handling
- HTTP 400: Bad request (invalid parameters)
- HTTP 401: Unauthorized (expired token - re-auth)
- HTTP 404: Resource not found
- HTTP 409: Conflict (resource already exists)

### Placement
- Linux cluster: Round-robin on workers 10.0.0.2-10.0.0.4
- OpenStack: Nova scheduler handles placement (ignore worker_ip in launch_vm)

## 📁 File Structure

```
lab1/
├── models.py                          # ✅ Updated with availability_zone
├── database.yaml                      # ✅ Multi-cluster configuration
├── remote_executor.py                 # ✅ Multi-NIC SSH support
├── orchestrator_api.py                # ✅ AZ routing logic
├── web_api.py                         # ✅ AZ endpoints
├── templates/dashboard.html           # ✅ AZ selector UI
│
├── providers/
│   ├── baremetal_provider.py          # ✅ Linux cluster (working)
│   ├── openstack_provider.py          # ⚠️ STUB - TO COMPLETE
│   ├── ovs_network_provider.py        # ✅ Linux networking (working)
│   └── base_compute.py                # ✅ Base class
│
└── openstack/                         # ⚠️ ALL STUBS - TO COMPLETE
    ├── __init__.py                    # ✅ Created
    ├── keystone_client.py             # ⚠️ STUB - Authentication
    ├── nova_client.py                 # ⚠️ STUB - Instances
    └── neutron_client.py              # ⚠️ STUB - Networks
```

## 🎯 Quick Start (Current State)

### Using Linux Cluster (Working)
```bash
# Start API
python3 main.py

# Access UI at http://localhost:8000
# Login: student / student
# Create slice → Select "Linux Cluster"
# Add VMs → Create links → Deploy
# VMs will launch on 10.0.0.x workers
```

### Enabling OpenStack (Future)
```bash
# 1. Complete implementation in openstack/*.py and providers/openstack_provider.py
# 2. Update database.yaml with correct OpenStack credentials
# 3. Test authentication: python3 -c "from openstack.keystone_client import KeystoneClient; ..."
# 4. Via UI: Create slice → Select "OpenStack Cluster"
# 5. VMs will deploy via OpenStack APIs to 10.0.1.x cluster
```

## 📚 Additional Resources

- OpenStack Keystone v3 API: https://docs.openstack.org/api-ref/identity/v3/
- OpenStack Nova v2.1 API: https://docs.openstack.org/api-ref/compute/
- OpenStack Neutron v2.0 API: https://docs.openstack.org/api-ref/network/v2/
- Lab 6 PDF: Original requirements document (user provided)

## ✅ Verification Checklist

Before considering OpenStack implementation complete:

- [ ] Can authenticate as admin and get unscoped token
- [ ] Can retrieve Cloud domain ID
- [ ] Can create project in Cloud domain
- [ ] Can create user in Cloud domain
- [ ] Can assign member role to user in project
- [ ] Can get scoped token for user
- [ ] Can create Neutron network and subnet
- [ ] Can create Neutron ports
- [ ] Can create Nova instance with ports
- [ ] Instance reaches ACTIVE state
- [ ] VMs can ping each other across Neutron network
- [ ] Can hot-plug interface to running instance
- [ ] Cirros VM activates interface after soft reboot
- [ ] Can delete instance
- [ ] Can delete ports and networks
- [ ] Full slice lifecycle: create → deploy → edit → delete

---

**Status**: Multi-cluster architecture ready. Linux cluster working. OpenStack stubs in place for future completion.
