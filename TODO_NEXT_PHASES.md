# Próximas Fases - Plan de Implementación

## 📋 Estado Actual
✅ **FASES 1-3 COMPLETADAS**
- Creación dinámica de interfaces
- API actualizada con nuevos endpoints
- Dashboard rediseñado con UX mejorado
- Topologías predefinidas (ring/bus/star/mesh)
- Export/Import JSON

---

## 🚧 FASE 4: Cloud-Init con cloud-localds (PENDIENTE)

### Objetivo
Usar `cloud-localds` para generar configuración de red automática en VMs Ubuntu, permitiendo que las interfaces dinámicas funcionen sin configuración manual.

### Tareas
1. **Actualizar `cloud_init_generator.py`:**
   - Reemplazar mkisofs con `cloud-localds`
   - Generar `user-data` y `network-config` separados
   - Formato cloud-init v2 para netplan

2. **Integrar en deployment:**
   - Llamar al generador antes de lanzar VM
   - Pasar cloud-init ISO a QEMU con `-drive`
   - Aplicar solo a VMs Ubuntu (Cirros no necesita)

3. **Configuración de red:**
   ```yaml
   network:
     version: 2
     ethernets:
       ens3:
         dhcp4: true  # Internet (VLAN 400)
       ens4:
         dhcp4: true  # Link 1
       ens5:
         dhcp4: true  # Link 2
   ```

### Archivos a Modificar
- `cloud_init_generator.py` - Lógica de generación
- `deployment_api.py` - Integración con create_vm
- `providers/baremetal_provider.py` - Agregar cloud-init ISO al launch_vm

### Comandos Necesarios
```bash
# Instalar cloud-image-utils si no existe
sudo apt install cloud-image-utils

# Generar cloud-init
cloud-localds seed.img user-data network-config
```

---

## 🚧 FASE 5: Integración noVNC (PENDIENTE)

### Objetivo
Permitir acceso VNC a las VMs directamente desde el navegador con click derecho.

### Tareas
1. **Instalar noVNC:**
   ```bash
   cd /opt
   git clone https://github.com/novnc/noVNC.git
   cd noVNC
   ./utils/novnc_proxy --vnc localhost:5900 --listen 6080
   ```

2. **Crear servicio systemd:**
   ```ini
   [Unit]
   Description=noVNC Proxy
   After=network.target

   [Service]
   Type=simple
   ExecStart=/opt/noVNC/utils/novnc_proxy --vnc localhost:5900 --listen 6080
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

3. **Agregar endpoint en `web_api.py`:**
   ```python
   @app.get("/api/vms/{vm_id}/vnc")
   async def get_vnc_url(vm_id: int, request: Request):
       """Retorna URL de noVNC para la VM"""
       vm = find_vm(vm_id)
       worker_ip = vm.worker_ip
       vnc_port = vm.vnc_port
       return {"vnc_url": f"http://{worker_ip}:6080/vnc.html?host={worker_ip}&port={vnc_port}"}
   ```

4. **Actualizar dashboard:**
   - Agregar click derecho en VMs
   - Menú contextual con "Access Console"
   - Abrir nueva pestaña con noVNC

### Archivos a Modificar
- `web_api.py` - Endpoint VNC
- `templates/dashboard.html` - Menú contextual

---

## 🚧 FASE 6: Sistema de Monitoreo (PENDIENTE)

### Objetivo
Mostrar métricas en tiempo real de VMs y workers con gráficos Chart.js.

### Tareas Completadas
✅ `monitoring/stats.py` - Algoritmo de Welford
✅ `monitoring/collector.py` - Lectura de cgroups v1
✅ `monitoring/monitor.py` - MonitorManager con threading

### Tareas Pendientes
1. **Integrar en main.py:**
   ```python
   from monitoring.monitor import MonitorManager
   
   monitor = MonitorManager(db, executor)
   monitor.start()  # Inicia thread de recolección
   ```

2. **Endpoints en web_api.py:**
   ```python
   @app.get("/api/metrics/vms")
   async def get_vm_metrics(request: Request):
       """Métricas de todas las VMs del usuario"""
       user = verify_session(request)
       role = db.get_user(user).get('role')
       
       if role == 'admin':
           # Ver todas las VMs
       else:
           # Ver solo sus VMs
       
       return db.data.get('vm_metrics', {})

   @app.get("/api/metrics/workers")
   async def get_worker_metrics(request: Request):
       """Métricas de workers (solo admin)"""
       user = verify_session(request)
       if db.get_user(user).get('role') != 'admin':
           raise HTTPException(403)
       
       return db.data.get('worker_metrics', {})
   ```

3. **Dashboard con Chart.js:**
   ```html
   <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
   
   <canvas id="cpuChart"></canvas>
   <canvas id="ramChart"></canvas>
   <canvas id="diskChart"></canvas>
   ```

4. **Vistas por rol:**
   - **Admin:** Ve todo + métricas de workers
   - **Student:** Ve solo sus slices y VMs

### Archivos a Modificar
- `main.py` - Iniciar MonitorManager
- `web_api.py` - 2 endpoints nuevos
- `templates/dashboard.html` - Gráficos Chart.js
- `requirements.txt` - Ya tiene numpy

### Métricas a Mostrar
- **Por VM:**
  - CPU usage (%)
  - RAM usage (MB) - Media (μ) y Desviación (σ)
  - Disk I/O (MB/s)
  - Network I/O (packets/s)

- **Por Worker:**
  - Total VMs corriendo
  - CPU total usado
  - RAM total usado
  - Disk disponible

---

## 🚧 FASE 7: Algoritmo Genético para VM Placement (PENDIENTE)

### Objetivo
Reemplazar round-robin con algoritmo genético que optimiza colocación de VMs basado en recursos.

### Conceptos
1. **Cromosoma:** Asignación de VMs a workers
   ```
   [VM1->Worker1, VM2->Worker3, VM3->Worker2, ...]
   ```

2. **Función Fitness:**
   - Balance de carga CPU
   - Balance de carga RAM
   - Balance de carga Disk
   - Penalización por sobreasignación

3. **Operadores Genéticos:**
   - **Crossover:** Intercambiar asignaciones entre soluciones
   - **Mutación:** Cambiar worker de una VM aleatoria
   - **Selección:** Torneo entre mejores soluciones

### Tareas
1. **Crear `genetic_placement.py`:**
   ```python
   class GeneticPlacement:
       def __init__(self, workers, vms, population_size=50, generations=100):
           self.workers = workers
           self.vms = vms
           ...
       
       def fitness(self, chromosome):
           """Evalúa qué tan buena es una asignación"""
           # Calcular balance de carga
           # Penalizar sobreasignaciones
           return score
       
       def evolve(self):
           """Ejecuta algoritmo genético"""
           # Población inicial aleatoria
           for gen in range(generations):
               # Evaluación fitness
               # Selección
               # Crossover
               # Mutación
           return best_solution
   ```

2. **Integrar en orchestrator:**
   ```python
   def deploy_slice(self, username, slice_id):
       vms = slice_data.get('vms', [])
       
       # Usar algoritmo genético
       from genetic_placement import GeneticPlacement
       ga = GeneticPlacement(self.workers, vms)
       placement = ga.evolve()
       
       # Asignar workers según resultado
       for vm, worker in placement.items():
           vm['worker_ip'] = worker
       
       # Continuar con deployment normal
   ```

3. **Logging del proceso:**
   - Mostrar generaciones
   - Fitness de mejor solución
   - Tiempo de ejecución

### Archivos a Crear/Modificar
- `genetic_placement.py` - NUEVO módulo
- `orchestrator_api.py` - Integrar en deploy_slice()
- `web_api.py` - Mostrar estado del placement en UI

---

## 📋 Resumen de Prioridades

| Fase | Prioridad | Complejidad | Tiempo Estimado |
|------|-----------|-------------|-----------------|
| **Fase 4: cloud-localds** | 🔴 Alta | Media | 2-3 horas |
| **Fase 5: noVNC** | 🟡 Media | Baja | 1-2 horas |
| **Fase 6: Monitoreo** | 🟡 Media | Media | 3-4 horas |
| **Fase 7: Algoritmo Genético** | 🟢 Baja | Alta | 4-6 horas |

---

## 🎯 Orden Sugerido de Implementación

1. **FASE 4 (cloud-localds)** - Crítico para Ubuntu VMs
2. **FASE 5 (noVNC)** - Mejora experiencia de usuario
3. **FASE 6 (Monitoreo)** - Visibilidad del sistema
4. **FASE 7 (Algoritmo Genético)** - Optimización avanzada

---

## 🐛 Issues Conocidos a Resolver

### 1. DHCP Timeout en VLAN 400
**Síntoma:** Error timeout de 10s al configurar dnsmasq
**Causa:** Comando grep tarda más de 10s
**Solución:** Ya aumentado a 30s en `providers/ovs_network_provider.py`

### 2. Cleanup Orphaned no actualiza contador
**Síntoma:** Al limpiar VMs huérfanas, el contador `used_vms` no disminuye
**Solución:** Implementar en `sync_manager.py`:
```python
def cleanup_orphaned_vms(self):
    for user in db.data['users'].values():
        actual_vms = count_real_vms(user['slices'])
        user['used_vms'] = actual_vms
```

### 3. Worker Discovery errors no críticos
**Síntoma:** Warnings al hacer sync si no hay VMs corriendo
**Estado:** No afecta funcionalidad, solo logs verbose

---

## 🔍 Testing Checklist

Antes de considerar cada fase completa:

- [ ] Crear slice nuevo
- [ ] Agregar VM con internet
- [ ] Agregar VM sin internet
- [ ] Crear enlace entre 2 VMs
- [ ] Verificar interfaces creadas automáticamente
- [ ] Editar VM (cambiar flavor)
- [ ] Crear topología preset (ring con 4 VMs)
- [ ] Exportar slice a JSON
- [ ] Importar slice desde JSON
- [ ] Deploy slice completo
- [ ] Verificar VMs corriendo en workers
- [ ] Verificar conectividad entre VMs
- [ ] Acceder por VNC (Fase 5)
- [ ] Ver métricas en dashboard (Fase 6)
- [ ] Eliminar slice y verificar cleanup

---

¿Por cuál fase quieres que continúe?
