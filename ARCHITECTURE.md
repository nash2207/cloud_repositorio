# Slice Manager Architecture

## Overview
Modular network slice orchestrator with pluggable compute and network providers.

## Architecture Layers

```
┌─────────────────────────────────────────────┐
│          Web API / CLI Interface            │
│         (web_api.py, cli.py)                │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│         Orchestrator API                    │
│      (orchestrator_api.py)                  │
│   - Slice lifecycle management              │
│   - Provider-agnostic operations            │
└────┬────────────────────────────────┬───────┘
     │                                │
┌────▼──────────┐          ┌─────────▼────────┐
│ Compute       │          │  Network          │
│ Provider      │          │  Provider         │
│ Interface     │          │  Interface        │
└────┬──────────┘          └─────────┬────────┘
     │                                │
┌────▼──────────┐          ┌─────────▼────────┐
│ BareMetalComputeProvider│ OVSNetworkProvider│
│ - QEMU/KVM VMs          │ - OVS + dnsmasq   │
│ - TAP interfaces        │ - VLAN management │
└─────────────────────────┴───────────────────┘

    Future: OpenStackComputeProvider, NeutronProvider
```

## Core Components

### 1. **Orchestrator API** (`orchestrator_api.py`)
- High-level slice management
- Delegates to pluggable providers
- Provider-agnostic VM and network operations

### 2. **Compute Providers** (`providers/`)
- **BaseComputeProvider**: Abstract interface
- **BareMetalComputeProvider**: QEMU/KVM implementation
- **Future: OpenStackComputeProvider**: Nova API calls

### 3. **Network Providers** (`providers/`)
- **BaseNetworkProvider**: Abstract interface
- **OVSNetworkProvider**: OpenVSwitch + dnsmasq
- **Future: NeutronProvider**: OpenStack networking

### 4. **Deployment API** (`deployment_api.py`)
- VM creation with flavor-aware interface naming
- QCOW2 image management
- MAC address generation

### 5. **Models** (`models.py`)
- **Flavor**: VM templates with interface naming rules
  - Cirros: eth0, eth1, eth2...
  - Ubuntu: ens3, ens4, ens5...
- **VM, Interface, Link, Slice**: Core data structures

### 6. **Database** (`database.py`)
- YAML-based persistence
- Thread-safe operations
- Slice, VM, and user management

### 7. **Sync Manager** (`sync_manager.py`)
- Worker state synchronization
- Orphaned VM detection
- Uses compute provider for scanning

## Data Flow: Deploy Slice

```
User Request
    ↓
Web API/CLI
    ↓
OrchestratorAPI.deploy_slice()
    ↓
    ├→ NetworkProvider.create_network() (for each VLAN)
    │   └→ OVS commands via RemoteExecutor
    ↓
    └→ ComputeProvider.launch_vm() (for each VM)
        └→ QEMU launch via RemoteExecutor
```

## Flavor-Aware Interface Naming

### Cirros VMs
- Management: **eth0** (VLAN 400 if internet enabled)
- Data: **eth1, eth2, eth3...**

### Ubuntu VMs
- Management: **ens3** (VLAN 400 if internet enabled)
- Data: **ens4, ens5, ens6...**

### Implementation
```python
Flavor.get_interface_name(flavor_name, index)
# cirros, 0 → eth0
# cirros, 1 → eth1
# ubuntu, 0 → ens3
# ubuntu, 1 → ens4
```

## Extending to OpenStack

### 1. Create OpenStack Compute Provider
```python
class OpenStackComputeProvider(BaseComputeProvider):
    def __init__(self, nova_client):
        self.nova = nova_client
    
    def launch_vm(self, worker_ip, vm_dict):
        # Use Nova API to launch instance
        server = self.nova.servers.create(...)
        return True, server.id
    
    def stop_vm(self, worker_ip, vm_dict):
        # Delete instance via Nova
        self.nova.servers.delete(vm_dict['pid'])
        return True
```

### 2. Create Neutron Network Provider
```python
class NeutronProvider(BaseNetworkProvider):
    def __init__(self, neutron_client):
        self.neutron = neutron_client
    
    def create_network(self, vlan_id, cidr, gateway_ip, dhcp_enabled=True):
        # Create network, subnet via Neutron API
        network = self.neutron.create_network(...)
        subnet = self.neutron.create_subnet(...)
        return True
```

### 3. Initialize Orchestrator with OpenStack Providers
```python
from providers.openstack_provider import OpenStackComputeProvider, NeutronProvider

# Initialize OpenStack clients
compute_provider = OpenStackComputeProvider(nova_client)
network_provider = NeutronProvider(neutron_client)

# Pass to orchestrator
orchestrator = OrchestratorAPI(
    db, deployment_api,
    compute_provider=compute_provider,
    network_provider=network_provider
)
```

## File Structure

```
.
├── main.py                    # Entry point
├── web_api.py                 # FastAPI web interface
├── cli.py                     # CLI interface
├── orchestrator_api.py        # Orchestrator (provider-agnostic)
├── deployment_api.py          # VM creation logic
├── models.py                  # Data models with flavor logic
├── database.py                # YAML persistence
├── sync_manager.py            # Worker sync with providers
├── qcow_manager.py            # QCOW2 image operations
├── remote_executor.py         # SSH command execution
├── worker_discovery.py        # Worker capability discovery
│
├── providers/
│   ├── __init__.py
│   ├── base_compute.py        # Abstract interfaces
│   ├── baremetal_provider.py  # QEMU/KVM implementation
│   └── ovs_network_provider.py# OVS + dnsmasq implementation
│
├── templates/
│   ├── login.html             # Web login
│   └── dashboard.html         # Web dashboard with Vis.js
│
├── ARCHITECTURE.md            # This file
└── README.md                  # User guide
```

## Deprecated Files (Can be removed)
- `vm_launcher.py` → replaced by `BareMetalComputeProvider`
- `vlan_manager.py` → replaced by `OVSNetworkProvider`
- `routing_manager.py` → not currently used
- `health_monitor.py` → not currently used
- `cloud_init_generator.py` → not currently used

## Benefits of This Architecture

1. **Modularity**: Clean separation of concerns
2. **Extensibility**: Easy to add OpenStack or other providers
3. **Testability**: Providers can be mocked for testing
4. **Maintainability**: Clear interfaces and single responsibility
5. **Flavor-Aware**: Automatic interface naming based on OS
6. **No Duplication**: Single source of truth for each operation

## Future Enhancements

1. **Multi-Backend Support**: Run some slices on bare-metal, others on OpenStack
2. **Load Balancing**: Intelligent worker selection based on load
3. **High Availability**: Redundant network nodes
4. **Monitoring**: Real-time VM health checks
5. **Auto-Scaling**: Dynamic worker pool management
