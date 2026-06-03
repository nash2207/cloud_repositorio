# Slice Manager - Network Slice Orchestrator

Modular network slice orchestrator with support for bare-metal (QEMU/KVM) and future OpenStack deployments.

## 🚀 Quick Start

### Installation

```bash
# Install dependencies
pip3 install -r requirements.txt
```

### Run

```bash
# Interactive mode - choose CLI, Web, or Both
python3 main.py

# Or directly:
python3 main.py --cli     # CLI only
python3 main.py --web     # Web only (http://0.0.0.0:8080)
python3 main.py --both    # Both CLI + Web simultaneously ⭐
```

## 📋 Requirements

- Python 3.8+
- FastAPI (for web interface)
- Uvicorn (ASGI server)
- PyYAML (database)
- SSH access to worker nodes
- OpenVSwitch on workers and network node

## 🏗️ Architecture

```
┌─────────────────────────────────────┐
│     main.py (Entry Point)           │
│  - Mode Selection (CLI/Web)         │
│  - System Initialization            │
│  - Worker Discovery & Sync          │
└─────────┬───────────────────────────┘
          │
     ┌────┴────┐
     │         │
┌────▼────┐ ┌─▼──────┐
│ CLI     │ │ Web API│
│ (cli.py)│ │(web_api)│
└────┬────┘ └─┬──────┘
     │        │
     └────┬───┘
          │
┌─────────▼───────────────────────────┐
│   Orchestrator API                  │
│   (orchestrator_api.py)             │
└─────┬──────────────────────┬────────┘
      │                      │
┌─────▼────────┐   ┌────────▼────────┐
│ Compute      │   │ Network         │
│ Provider     │   │ Provider        │
│ (pluggable)  │   │ (pluggable)     │
└──────────────┘   └─────────────────┘
```

## 🎯 Features

### Core Functionality
- ✅ Create network slices with isolated VLANs
- ✅ Deploy VMs with multiple flavors (Cirros, Ubuntu)
- ✅ Create L2 links between VMs
- ✅ Internet access via VLAN 400
- ✅ DHCP server per VLAN (dnsmasq)
- ✅ Round-robin VM placement
- ✅ Worker synchronization
- ✅ Orphaned VM cleanup

### Interfaces
- 🖥️ **CLI**: Interactive command-line interface
- 🌐 **Web**: Modern web dashboard with:
  - Real-time topology visualization (Vis.js)
  - Drag & drop link creation
  - Deploy status polling
  - Resource quota monitoring
  - Dark mode UI

### Supported Flavors
- **Cirros** (1GB): `eth0, eth1, eth2...`
- **Ubuntu** (2.2GB): `ens3, ens4, ens5...`

## 📖 Usage Examples

### Both CLI + Web Mode (Recommended) ⭐

```bash
python3 main.py --both

# Web interface runs in background on http://0.0.0.0:8080
# CLI runs in foreground for quick operations
# Use whichever interface you prefer!
```

### CLI Mode

```bash
python3 main.py --cli

# Follow interactive menu:
# 1. Create user
# 2. Create slice
# 3. Add VM to slice
# 4. Create link between VMs
# 5. List slices
# 6. Deploy slice
# 7. Delete slice
```

### Web Mode

```bash
python3 main.py --web

# Access: http://0.0.0.0:8080
# Login with credentials
# Use web interface to:
#  - Create slices
#  - Add VMs (select flavor: cirros/ubuntu)
#  - Create links (click mode or form)
#  - Deploy slices
#  - View topology
```

## 🔧 Configuration

### Worker Nodes
Default workers are configured in `database.yaml`:
```yaml
workers_list:
  - 10.0.10.1  # Worker 1
  - 10.0.10.2  # Worker 2
  - 10.0.10.3  # Worker 3 (also network node)
```

### Network Node
Network node (10.0.10.3) handles:
- DHCP servers (dnsmasq in namespaces)
- VLAN gateways
- Internet access via VLAN 400

### Base Images
Images should be located at:
- `/tmp/vm_images/cirros-0.6.2-x86_64-disk.img`
- `/tmp/vm_images/focal-server-cloudimg-amd64.img`

## 🧩 Extending to OpenStack

The architecture supports pluggable providers. To add OpenStack:

```python
# providers/openstack_provider.py
from providers.base_compute import BaseComputeProvider

class OpenStackComputeProvider(BaseComputeProvider):
    def __init__(self, nova_client):
        self.nova = nova_client
    
    def launch_vm(self, worker_ip, vm_dict):
        # Use Nova API
        server = self.nova.servers.create(...)
        return True, server.id
```

Then initialize orchestrator with OpenStack provider:
```python
from providers.openstack_provider import OpenStackComputeProvider

compute_provider = OpenStackComputeProvider(nova_client)
orchestrator = OrchestratorAPI(db, deployment, compute_provider=compute_provider)
```

## 📁 Project Structure

```
.
├── main.py                    # Entry point with mode selection
├── cli.py                     # CLI interface
├── web_api.py                 # Web API (FastAPI)
├── orchestrator_api.py        # Slice orchestration (provider-agnostic)
├── deployment_api.py          # VM creation with flavor awareness
├── models.py                  # Data models (Slice, VM, Link, Flavor)
├── database.py                # YAML persistence
├── sync_manager.py            # Worker synchronization
├── qcow_manager.py            # QCOW2 image management
├── remote_executor.py         # SSH command execution
├── worker_discovery.py        # Worker capability discovery
│
├── providers/
│   ├── base_compute.py        # Abstract interfaces
│   ├── baremetal_provider.py  # QEMU/KVM implementation
│   └── ovs_network_provider.py# OVS + dnsmasq implementation
│
├── templates/
│   ├── login.html             # Web login page
│   └── dashboard.html         # Web dashboard
│
├── requirements.txt           # Python dependencies
├── README.md                  # This file
└── ARCHITECTURE.md            # Detailed architecture docs
```

## 🐛 Troubleshooting

### Web interface not accessible
```bash
# Check if server is running
netstat -tulpn | grep 8080

# Check logs
python3 main.py --web
```

### VMs not getting DHCP
```bash
# Check dnsmasq processes on network node
ssh ubuntu@10.0.10.3 "ps aux | grep dnsmasq"

# Check DHCP namespaces
ssh ubuntu@10.0.10.3 "sudo ip netns list"
```

### Orphaned VMs
```bash
# From CLI
python3 main.py --cli
# Choose option 8: Cleanup orphaned VMs

# From Web
# Login → Click "Cleanup Orphaned" button
```

## 🔒 Security Notes

- SSH keys must be configured for password-less access to workers
- Web sessions are stored in-memory (use Redis/JWT for production)
- Passwords are hashed with SHA256 (use bcrypt for production)
- No HTTPS enabled (add nginx reverse proxy for production)

## 📝 License

Educational project - Universidad Politécnica de Madrid

## 🤝 Contributing

This is an academic project. For improvements, contact the maintainers.

## 📧 Support

For issues or questions, refer to ARCHITECTURE.md for detailed technical documentation.
