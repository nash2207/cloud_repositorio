# Arquitectura del Sistema - Slice Manager

## 📐 Visión General

Sistema orquestador de slices de red con soporte multi-cluster (Linux bare-metal y OpenStack). Permite crear topologías de VMs con enlaces L2, gestión de VLANs, y despliegue automático con placement inteligente mediante algoritmo genético.

---

## 🗂️ Estructura de Archivos y Responsabilidades

### 🎯 **Core - Orquestación**

#### `orchestrator_api.py` ⭐ **ARCHIVO PRINCIPAL**
**Responsabilidad**: API de alto nivel para gestión de slices. Rutea operaciones a los providers correctos según la zona de disponibilidad (AZ).

**Funciones clave**:
- `create_slice(username, slice_name, topology_type, availability_zone)` - Crea slice en AZ específica
- `add_vm_to_slice()` - Añade VM (llama a algoritmo genético para placement)
- `create_link()` - Crea enlace L2 entre VMs, genera interfaces dinámicamente
- `deploy_slice()` - **Punto de entrada del deployment**. Rutea a Linux o OpenStack provider
- `delete_slice()` - Limpieza de recursos

**Integración con Algoritmo Genético**:
```python
# En add_vm_to_slice(), llama a:
worker_ip = self.get_next_worker(availability_zone)  # ← Actualmente round-robin
# AQUÍ deberás integrar tu algoritmo genético para placement óptimo
```

**Dónde integrar OpenStack**:
- Método `deploy_slice()` tiene condicional `if availability_zone == "openstack"`
- Actualmente retorna error, implementar llamadas al `openstack_provider.py`

---

#### `deployment_api.py`
**Responsabilidad**: Gestión de VMs a nivel de infraestructura (QCOW, VNC ports, interfaces).

**Funciones clave**:
- `create_vm_with_qcow()` - Crea VM con imagen QCOW2, asigna puerto VNC, interfaces
- `delete_vm_dict()` - Elimina imágenes QCOW2 de workers
- `assign_vnc_port()` - Asigna puertos VNC únicos (5901+)

**Nota**: Este módulo es específico de Linux cluster. OpenStack no usa QCOW2 locales.

---

#### `web_api.py`
**Responsabilidad**: API REST (FastAPI) y WebSocket para UI web.

**Endpoints importantes**:
- `POST /api/slices` - Crea slice (incluye parámetro `availability_zone`)
- `POST /api/slices/{id}/vms` - Añade VM
- `POST /api/slices/{id}/links` - Crea enlace
- `POST /api/slices/{id}/deploy` - Despliega slice
- `GET /api/vms/{vm_id}/console` - Obtiene URL de consola noVNC
- `WebSocket /vnc_ws/{proxy_port}` - Proxy WebSocket para VNC

**Flujo de llamadas**:
```
UI → web_api.py → orchestrator_api.py → provider (Linux/OpenStack)
```

---

### 🖥️ **Providers - Drivers de Infraestructura**

#### `providers/baremetal_provider.py` ✅ **LINUX CLUSTER (FUNCIONANDO)**
**Responsabilidad**: Driver para cluster Linux con QEMU/KVM.

**Funciones clave**:
- `launch_vm(worker_ip, vm_dict)` - Lanza QEMU con interfaces TAP + OVS
- `stop_vm(worker_ip, vm_dict)` - Mata proceso QEMU, limpia TAPs
- `get_running_vms(worker_ip)` - Escanea procesos QEMU en worker

**Comandos que ejecuta**:
```bash
# Crea TAP y conecta a OVS con VLAN
sudo ip tuntap add mode tap name tap_1004_eth1
sudo ovs-vsctl add-port br-int tap_1004_eth1 tag=160

# Lanza QEMU
qemu-system-x86_64 -enable-kvm -m 512 -vnc 0.0.0.0:1 \
  -netdev tap,id=net0,ifname=tap_1004_eth1 \
  -device e1000,netdev=net0,mac=... \
  -drive file=/home/ubuntu/vm_images/vm1_img.qcow2
```

---

#### `providers/openstack_provider.py` ⚠️ **OPENSTACK CLUSTER (STUB)**
**Responsabilidad**: Driver para cluster OpenStack vía REST APIs nativas.

**Funciones a implementar**:
- `launch_vm()` - Crear instancia en OpenStack
- `stop_vm()` - Eliminar instancia
- `_setup_project()` - Crear proyecto Keystone para slice
- `_create_network_for_link()` - Crear red Neutron para enlace
- `_create_port_for_interface()` - Crear puerto Neutron para interfaz VM

**Flujo OpenStack** (a implementar):
```python
# 1. Autenticación admin
keystone.get_admin_token()
keystone.get_cloud_domain_id()

# 2. Setup proyecto
project_id = keystone.create_project(f"slice_{slice_id}")
user_id = keystone.create_user(f"user_slice_{slice_id}")
keystone.assign_role(project_id, user_id, "member")
scoped_token = keystone.get_scoped_token(user, password, project_id)

# 3. Para cada Link → Neutron network
network_id = neutron.create_network(scoped_token, project_id, "net_link1")
subnet_id = neutron.create_subnet(scoped_token, network_id, "192.168.1.0/24")

# 4. Para cada VM interface → Neutron port
port_id = neutron.create_port(scoped_token, network_id, "port_vm1_eth1")

# 5. Lanzar VM con ports
nova.create_instance(scoped_token, name, flavor_id, image_id, [port_ids])
```

---

#### `providers/ovs_network_provider.py` ✅ **LINUX NETWORKING (FUNCIONANDO)**
**Responsabilidad**: Gestión de VLANs, DHCP (dnsmasq), namespaces en network node.

**Funciones clave**:
- `create_network(vlan_id, cidr, gateway_ip)` - Crea VLAN en OVS + namespace + dnsmasq
- `delete_network(vlan_id)` - Limpia namespace y dnsmasq

**Comandos que ejecuta** (en network node 10.0.0.1):
```bash
# Crear namespace DHCP
sudo ip netns add ns-dhcp-vlan160

# Crear puerto gateway en OVS
sudo ovs-vsctl add-port br-int gw_vlan160 tag=160 -- set interface gw_vlan160 type=internal

# Configurar IP en namespace
sudo ip link set gw_vlan160 netns ns-dhcp-vlan160
sudo ip netns exec ns-dhcp-vlan160 ip addr add 192.168.160.1/24 dev gw_vlan160
sudo ip netns exec ns-dhcp-vlan160 ip link set gw_vlan160 up

# Iniciar dnsmasq
sudo ip netns exec ns-dhcp-vlan160 dnsmasq \
  --interface=gw_vlan160 \
  --dhcp-range=192.168.160.10,192.168.160.200,12h
```

**Para OpenStack**: Este provider NO se usa. Neutron maneja todo internamente.

---

### 🧬 **Algoritmo Genético (VM Placement)**

#### **Ubicación actual**: `orchestrator_api.py` → método `get_next_worker(availability_zone)`

**Estado actual**: Round-robin simple
```python
def get_next_worker(self, availability_zone="linux"):
    cluster_config = self._get_cluster_config(availability_zone)
    workers = cluster_config.get("workers", [])
    
    idx = self.round_robin_idx.get(availability_zone, 0)
    worker = workers[idx % len(workers)]
    self.round_robin_idx[availability_zone] = idx + 1
    return worker
```

**Dónde integrar tu Algoritmo Genético**:

Crea archivo `vm_placement.py` con tu algoritmo:
```python
class GeneticPlacement:
    def __init__(self, workers_info, availability_zone):
        self.workers = workers_info  # {worker_ip: {max_ram, used_ram, ...}}
        self.az = availability_zone
    
    def find_optimal_worker(self, vm_requirements):
        """
        Algoritmo genético para placement
        
        Args:
            vm_requirements: {cores, ram_gb, disk_gb}
        
        Returns:
            worker_ip: IP del worker óptimo
        """
        # TU ALGORITMO GENÉTICO AQUÍ
        # Cromosoma: [worker_idx]
        # Fitness: Balanceo de carga, latencia, capacidad restante
        pass
```

Luego en `orchestrator_api.py`:
```python
from vm_placement import GeneticPlacement

def add_vm_to_slice(self, username, slice_id, vm_name, flavor_name, internet_enabled=False):
    # ...
    availability_zone = slice_data.get("availability_zone", "linux")
    
    # Obtener workers del cluster
    cluster_workers = self._get_cluster_config(availability_zone)["workers"]
    workers_info = {w: self.db.data["workers"][w] for w in cluster_workers}
    
    # Obtener requirements de flavor
    flavor_spec = Flavor.get(flavor_name)
    vm_requirements = {
        "cores": flavor_spec["cores"],
        "ram_gb": flavor_spec["ram_gb"],
        "disk_gb": flavor_spec["disk_gb"]
    }
    
    # LLAMAR ALGORITMO GENÉTICO
    ga = GeneticPlacement(workers_info, availability_zone)
    worker_ip = ga.find_optimal_worker(vm_requirements)
    
    # Continuar con deployment...
```

**Consideraciones por AZ**:
- **Linux**: 4 workers (10.0.0.1-4), recursos limitados, considerar capacidad restante
- **OpenStack**: 3 workers (10.0.1.2-4), pero el placement lo decide Nova scheduler internamente. Tu GA solo selecciona entre proyectos/availability zones de OpenStack.

---

### 📊 **Modelos de Datos**

#### `models.py`
**Clases principales**:

```python
class Slice:
    def __init__(self, slice_id, owner, topology_type, availability_zone):
        self.availability_zone = availability_zone  # "linux" o "openstack"
        self.vlan_pool_start = 100 + (slice_id % 100) * 20  # Pool de 20 VLANs
        self.vms = []
        self.links = []
        self.status = "design"  # design → provisioning → deployed

class VM:
    def __init__(self, vm_id, name, owner, worker_ip, vnc_port, interfaces, flavor):
        self.flavor = flavor  # "cirros" o "ubuntu"
        self.interfaces = [Interface(...)]  # Lista de interfaces
        self.status = "design"
    
    def get_next_interface_name(self):
        # Genera eth0, eth1... (Cirros) o ens3, ens4... (Ubuntu)
        pass

class Link:
    def __init__(self, link_id, vlan_id, vm1_id, vm1_interface, vm2_id, vm2_interface):
        # Representa enlace L2 entre dos VMs
        pass

class Flavor:
    FLAVORS = {
        "cirros": {"cores": 1, "ram_gb": 0.5, "disk_gb": 1},
        "ubuntu": {"cores": 1, "ram_gb": 0.5, "disk_gb": 2.2}
    }
```

---

#### `database.yaml`
**Configuración de clusters**:
```yaml
clusters:
  linux:
    bind_address: "10.0.0.6"  # IP del nodo app para SSH a este cluster
    network_node: "10.0.0.1"
    switch_node: "10.0.0.7"
    workers: ["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4"]
  
  openstack:
    bind_address: "10.0.1.6"
    headnode: "10.0.1.1"  # OpenStack API endpoint
    workers: ["10.0.1.2", "10.0.1.3", "10.0.1.4"]

workers:
  10.0.0.1:
    max_vms: 10
    max_ram_gb: 1
    max_cores: 2
    used_ram_gb: 0  # ← Actualizado dinámicamente por sync_manager
    cluster: linux
  # ...

users:
  admin:
    role: admin
    quota_vms: 100
    slices: []

slices: {}  # Se puebla dinámicamente
```

---

### 🔄 **Sincronización y Monitoreo**

#### `sync_manager.py`
**Responsabilidad**: Sincroniza estado de VMs entre base de datos y workers.

**Funciones clave**:
- `sync_vms_from_workers()` - Escanea workers, actualiza PIDs de VMs
- `cleanup_orphaned_vms()` - Mata VMs huérfanas (no en BD)
- `_recalculate_user_quotas()` - Recalcula `used_vms` por usuario

**Flujo**:
```python
# Al iniciar la app (main.py)
sync_manager.sync_vms_from_workers()

# Periódicamente (cada 30s)
while True:
    sync_manager.sync_vms_from_workers()
    time.sleep(30)
```

---

#### `vnc_proxy.py`
**Responsabilidad**: Gestiona procesos websockify para acceso VNC via navegador.

**Funciones clave**:
- `get_proxy_port(worker_ip, vnc_port)` - Crea proxy websockify: `localhost:6080 → 10.0.0.1:5901`
- `stop_proxy(proxy_port)` - Detiene websockify

**Cómo funciona**:
1. Usuario hace clic en "Console" en una VM deployed
2. `web_api.py` llama `vnc_proxy_manager.get_proxy_port(worker_ip, vnc_port)`
3. Se inicia: `websockify 0.0.0.0:6080 10.0.0.1:5901`
4. FastAPI WebSocket `/vnc_ws/6080` hace relay: `navegador ↔ FastAPI ↔ websockify ↔ VM VNC`
5. noVNC en el navegador se conecta a `ws://localhost:8080/vnc_ws/6080`

---

### 🌐 **Networking**

#### `remote_executor.py`
**Responsabilidad**: Ejecuta comandos SSH en workers/network node.

**Características**:
- Soporte multi-NIC con `bind_address` para diferentes clusters
- `execute_direct(remote_ip, command, bind_address=None)`

**Ejemplo**:
```python
executor.set_bind_address("10.0.0.6")  # Para cluster Linux
executor.execute_direct("10.0.0.1", "sudo ovs-vsctl show")
```

**Para OpenStack**: No se usa (solo llamadas REST a API)

---

#### `vlan_manager.py`, `routing_manager.py`
**Responsabilidad**: Helpers para gestión de VLANs y rutas (específico de Linux).

**Para OpenStack**: No aplica (Neutron maneja VLANs internamente).

---

### 🖼️ **UI y Plantillas**

#### `templates/dashboard.html`
**Responsabilidad**: Interfaz web (HTML + JavaScript + Vis.js para topología).

**Flujo UI**:
1. **Crear Slice**: Selector de AZ (Linux/OpenStack) → `POST /api/slices`
2. **Añadir VMs**: Botón "Add VM" → `POST /api/slices/{id}/vms`
3. **Crear Links**: Modo link (clic en 2 VMs) → `POST /api/slices/{id}/links`
4. **Deploy**: Botón "Deploy" → `POST /api/slices/{id}/deploy`
5. **Console**: Clic en VM deployed → `GET /api/vms/{id}/console` → Abre noVNC

**Visualización**: Vis.js dibuja grafo con VMs (nodos) y Links (aristas con label de VLAN).

---

## 🔧 Implementación de OpenStack

### **Archivos a editar**:

#### 1. `openstack/keystone_client.py` (STUB)
Implementar métodos de autenticación:
- `get_admin_token()`
- `get_cloud_domain_id()`
- `create_project()`
- `create_user()`
- `assign_role()`
- `get_scoped_token()`

**APIs**:
- POST `http://10.0.1.1:5000/v3/auth/tokens`
- GET `http://10.0.1.1:5000/v3/domains`
- POST `http://10.0.1.1:5000/v3/projects`
- POST `http://10.0.1.1:5000/v3/users`
- PUT `http://10.0.1.1:5000/v3/projects/{project_id}/users/{user_id}/roles/{role_id}`

#### 2. `openstack/neutron_client.py` (STUB)
Implementar métodos de red:
- `create_network(token, project_id, network_name)`
- `create_subnet(token, network_id, cidr)`
- `create_port(token, network_id, port_name)`
- `delete_network()`, `delete_port()`

**APIs**:
- POST `http://10.0.1.1:9696/v2.0/networks`
- POST `http://10.0.1.1:9696/v2.0/subnets`
- POST `http://10.0.1.1:9696/v2.0/ports`

#### 3. `openstack/nova_client.py` (STUB)
Implementar métodos de compute:
- `create_instance(token, name, flavor_id, image_id, port_ids)`
- `wait_for_active(token, server_id)`
- `delete_instance(token, server_id)`
- `attach_interface()` (para hot-plug)
- `soft_reboot()` (para Cirros)

**APIs**:
- POST `http://10.0.1.1:8774/v2.1/servers`
- GET `http://10.0.1.1:8774/v2.1/servers/{server_id}`
- DELETE `http://10.0.1.1:8774/v2.1/servers/{server_id}`
- POST `http://10.0.1.1:8774/v2.1/servers/{server_id}/os-interface`

#### 4. `providers/openstack_provider.py` (STUB)
Orquestar llamadas a clientes:
```python
def launch_vm(self, worker_ip, vm_dict):
    # 1. Setup proyecto si no existe
    if slice_id not in self.project_ids:
        project_info = self._setup_project(slice_id, slice_owner)
        scoped_token = project_info["token"]
    
    # 2. Crear ports para cada interface
    port_ids = []
    for iface in vm_dict["interfaces"]:
        link = find_link_by_interface(iface)
        network_id = self._get_or_create_network_for_link(token, project_id, link)
        port = neutron.create_port(token, network_id, f"port_{vm_name}_{iface_name}")
        port_ids.append(port["port_id"])
    
    # 3. Lanzar instancia
    result = nova.create_instance(token, vm_name, flavor_id, image_id, port_ids)
    
    # 4. Esperar ACTIVE
    nova.wait_for_active(token, result["server_id"])
    
    return True, result["server_id"]
```

#### 5. `orchestrator_api.py` → `deploy_slice()`
Completar bloque OpenStack:
```python
elif availability_zone == "openstack":
    # Para cada link: crear red Neutron
    for link in slice_data.get("links", []):
        compute_provider._create_network_for_link(scoped_token, project_id, link)
    
    # Para cada VM: crear ports + lanzar instancia
    for vm_dict in slice_data.get("vms", []):
        success, server_id = compute_provider.launch_vm(None, vm_dict)
        if success:
            vm_dict["status"] = "deployed"
            vm_dict["server_id"] = server_id  # Guardar server_id (no PID)
```

---

## 🧪 Testing

### Linux Cluster (Actual):
```bash
python3 main.py
# Login: admin/admin
# Create slice AZ=linux → Add VMs → Create links → Deploy
```

### OpenStack (Futuro):
```bash
# 1. Probar autenticación
python3 -c "
from openstack.keystone_client import KeystoneClient
k = KeystoneClient('http://10.0.1.1:5000')
success, token = k.get_admin_token('cloud_admin', 'admin')
print(f'Token: {token[:20]}...')
"

# 2. Create slice AZ=openstack → Add VMs → Deploy
```

---

## 📂 Resumen de Dependencias

```
orchestrator_api.py (ruteo por AZ)
    ├─→ providers/baremetal_provider.py (Linux)
    │       ├─→ remote_executor.py (SSH commands)
    │       ├─→ deployment_api.py (QCOW, VNC)
    │       └─→ providers/ovs_network_provider.py (VLANs, DHCP)
    │
    └─→ providers/openstack_provider.py (OpenStack - STUB)
            ├─→ openstack/keystone_client.py (Auth)
            ├─→ openstack/neutron_client.py (Networks)
            └─→ openstack/nova_client.py (Instances)

web_api.py (FastAPI REST + WebSocket)
    └─→ orchestrator_api.py

sync_manager.py (Sincronización)
    └─→ providers/baremetal_provider.get_running_vms()

vnc_proxy.py (WebSocket relay)
    └─→ websockify (subproceso)
```

---

## 🎯 Próximos Pasos

1. **Algoritmo Genético**: Crear `vm_placement.py` e integrar en `orchestrator_api.add_vm_to_slice()`
2. **OpenStack Auth**: Completar `keystone_client.py` y probar tokens
3. **OpenStack Networking**: Completar `neutron_client.py` y crear networks de prueba
4. **OpenStack Compute**: Completar `nova_client.py` y lanzar instancia de prueba
5. **OpenStack Provider**: Integrar todo en `openstack_provider.py`
6. **Deploy OpenStack**: Habilitar bloque en `orchestrator_api.deploy_slice()`
7. **Testing**: Crear slice AZ=openstack y verificar deployment end-to-end
