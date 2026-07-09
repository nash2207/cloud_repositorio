"""
Genetic Algorithm for VM Placement - ORCHESTRATOR LAYER
Uses pure mathematical functions from math_functions module
Delegates I/O to TelemetryAdapter
Infrastructure-agnostic optimization engine
"""
import logging
import math
from typing import List, Dict, Tuple

from math_functions.genetic_algorithm import genetic_algorithm
from math_functions.resource_calculator import (
    calculate_confidence_bound,
    calculate_dimensionless_delta,
    calculate_dimensionless_rho,
    calculate_weighted_penalty,
    calculate_weighted_imbalance,
    calculate_fitness,
    calculate_gamma_barrier
)
from telemetry_adapter import TelemetryAdapter

logger = logging.getLogger(__name__)


class VMPlacementGA:
    """
    VM Placement Orchestrator
    
    Responsibilities:
    - Coordinate between telemetry (I/O) and math (pure functions)
    - Build fitness function callback for GA
    - Translate GA output to infrastructure placement
    
    Does NOT contain:
    - Raw mathematical logic (delegated to math_functions)
    - I/O operations (delegated to TelemetryAdapter)
    """
    
    # Resource weights (must sum to 1.0)
    W_RAM = 0.50  # RAM is incompressible (OOM Killer)
    W_CPU = 0.30  # CPU is compressible (Latency)
    W_DISK = 0.20  # Disk is static
    
    def __init__(self, monitoring_system, cluster_config, availability_zone):
        """
        Initialize VM Placement Orchestrator
        
        Args:
            monitoring_system: MonitoringSystem instance
            cluster_config: Cluster configuration dict
            availability_zone: "linux" or "openstack"
        """
        self.telemetry = TelemetryAdapter(monitoring_system)
        self.cluster_config = cluster_config
        self.availability_zone = availability_zone
        self.workers = cluster_config.get("workers", [])
        
        # GA parameters
        self.population_size = 50
        self.generations = 100
        self.mutation_rate = 0.15
        self.elite_size = 5
        
        # Confidence factor K for statistical oversubscription
        # K = 1.645 for 90% confidence (one-sided)
        self.K_cpu = 1.645
        self.K_ram = 1.645
        
        # Calculate Γ (barrier penalty) using pure function
        N = len(self.workers)
        w_min = min(self.W_RAM, self.W_CPU, self.W_DISK)  # 0.20
        epsilon = 0.01
        self.GAMMA = calculate_gamma_barrier(N, w_min, epsilon)
        
        logger.info(f"GA initialized for {availability_zone} cluster:")
        logger.info(f"  - Workers (N): {N}")
        logger.info(f"  - w_min (disk): {w_min}")
        logger.info(f"  - ε (tolerance): {epsilon}")
        logger.info(f"  - Γ (barrier penalty): {self.GAMMA:.0f}")
        logger.info(f"  - K_cpu (confidence): {self.K_cpu}")
        logger.info(f"  - K_ram (confidence): {self.K_ram}")
    
    def calculate_placement(self, vms_to_place: List[Dict]) -> Tuple[Dict[int, str], str]:
        """
        Calculate optimal VM placement using Genetic Algorithm
        
        Orchestration method: Coordinates I/O and pure math
        
        Args:
            vms_to_place: List of VM dicts with {vm_id, flavor}
        
        Returns:
            Tuple[Dict[int, str], str]:
                - {vm_id: worker_ip, ...}
                - Explanation log
        """
        if not vms_to_place:
            return {}, "No VMs to place"
        
        if not self.workers:
            return {}, f"No workers available in {self.availability_zone} cluster"
        
        logger.info(f"Starting GA placement for {len(vms_to_place)} VMs on {len(self.workers)} workers")
        
        # I/O: Fetch current worker states
        workers_state = self.telemetry.get_workers_state(self.workers)
        
        # Build fitness function (closure with captured state)
        def fitness_func(chromosome: List[int]) -> float:
            return self._evaluate_fitness(chromosome, vms_to_place, workers_state)
        
        # Run GA (pure mathematical optimization)
        best_solution, best_fitness, fitness_history = genetic_algorithm(
            chromosome_length=len(vms_to_place),
            gene_range=(0, len(self.workers) - 1),
            fitness_func=fitness_func,
            population_size=self.population_size,
            generations=self.generations,
            mutation_rate=self.mutation_rate,
            elite_size=self.elite_size
        )
        
        # Translate solution to placement map
        placement = {}
        for i, vm in enumerate(vms_to_place):
            worker_idx = best_solution[i]
            placement[vm['vm_id']] = self.workers[worker_idx]
        
        # Generate explanation
        explanation = self._generate_explanation(
            vms_to_place, placement, workers_state, best_fitness
        )
        
        logger.info(f"GA placement completed: fitness={best_fitness:.2f}")
        logger.info(f"Placement: {placement}")
        
        return placement, explanation
    
    def _evaluate_fitness(self, solution: List[int], vms: List[Dict], workers_state: Dict) -> float:
        """
        Evaluate fitness for a solution (chromosome)
        
        Uses pure functions from resource_calculator module
        
        Args:
            solution: Chromosome [worker_idx_vm1, worker_idx_vm2, ...]
            vms: List of VMs to place
            workers_state: Current worker states
        
        Returns:
            float: Fitness score (higher is better)
        
        Formula:
            F(X) = -[Γ · Σ(w_c · Δ²)] - Σ(w_c · ρ²)
        """
        # Build worker assignments
        worker_assignments = {worker_ip: [] for worker_ip in self.workers}
        for vm_idx, worker_idx in enumerate(solution):
            worker_ip = self.workers[worker_idx]
            worker_assignments[worker_ip].append(vms[vm_idx])
        
        total_penalty = 0.0
        total_imbalance = 0.0
        
        resource_weights = {
            'cpu': self.W_CPU,
            'ram': self.W_RAM,
            'disk': self.W_DISK
        }
        
        for worker_ip, assigned_vms in worker_assignments.items():
            worker_state = workers_state[worker_ip]
            capacity = worker_state['capacity']
            current_usage = worker_state['usage']
            
            # Calculate projected load with confidence bounds
            new_load = self._calculate_load_with_confidence(
                assigned_vms, current_usage, capacity
            )
            
            # Calculate Δ (overload) for each resource using pure function
            deltas = {
                'cpu': calculate_dimensionless_delta(new_load['cpu'], capacity['cores']),
                'ram': calculate_dimensionless_delta(new_load['ram'], capacity['ram_mb']),
                'disk': calculate_dimensionless_delta(new_load['disk'], capacity['disk_gb'])
            }
            
            # Calculate ρ (utilization) for each resource using pure function
            rhos = {
                'cpu': calculate_dimensionless_rho(new_load['cpu'], capacity['cores']),
                'ram': calculate_dimensionless_rho(new_load['ram'], capacity['ram_mb']),
                'disk': calculate_dimensionless_rho(new_load['disk'], capacity['disk_gb'])
            }
            
            # Penalty term using pure function
            penalty = calculate_weighted_penalty(deltas, resource_weights)
            total_penalty += penalty
            
            # Imbalance term using pure function
            imbalance = calculate_weighted_imbalance(rhos, resource_weights)
            total_imbalance += imbalance
        
        # Master fitness function using pure function
        fitness = calculate_fitness(total_penalty, total_imbalance, self.GAMMA)
        
        return fitness
    
    def _calculate_load_with_confidence(self, new_vms: List[Dict], 
                                       current_usage: Dict, 
                                       capacity: Dict) -> Dict:
        """
        Calculate expected load using Central Limit Theorem
        
        Uses pure function: calculate_confidence_bound()
        
        Args:
            new_vms: VMs to be added
            current_usage: Current usage stats
            capacity: Worker capacity
        
        Returns:
            Dict: {'cpu': float, 'ram': float, 'disk': float}
        
        Formula:
            Confidence = Σμ + K * √(Σσ²)
        """
        # Current load (mean + K * std_dev) using pure function
        current_cpu_confidence = calculate_confidence_bound(
            current_usage['cpu']['mean'],
            current_usage['cpu']['std_dev'],
            self.K_cpu
        )
        current_ram_confidence = calculate_confidence_bound(
            current_usage['ram']['mean'],
            current_usage['ram']['std_dev'],
            self.K_ram
        )
        current_disk = current_usage['disk']['allocated_gb']
        
        # New VMs load (use default usage stats from telemetry)
        if len(new_vms) > 0:
            flavor = new_vms[0].get('flavor', 'ubuntu')
            default_usage = self.telemetry.get_vm_default_usage_stats(flavor)
            
            new_cpu_mean = len(new_vms) * default_usage['cpu']['mean']
            new_cpu_variance = len(new_vms) * (default_usage['cpu']['std_dev'] ** 2)
            new_cpu_confidence = new_cpu_mean + self.K_cpu * math.sqrt(new_cpu_variance)
            
            new_ram_mean = len(new_vms) * default_usage['ram']['mean']
            new_ram_variance = len(new_vms) * (default_usage['ram']['std_dev'] ** 2)
            new_ram_confidence = new_ram_mean + self.K_ram * math.sqrt(new_ram_variance)
            
            resources = self.telemetry.get_vm_flavor_resources(flavor)
            new_disk = len(new_vms) * resources['disk_gb']
        else:
            new_cpu_confidence = 0
            new_ram_confidence = 0
            new_disk = 0
        
        return {
            'cpu': current_cpu_confidence + new_cpu_confidence,
            'ram': current_ram_confidence + new_ram_confidence,
            'disk': current_disk + new_disk
        }
    
    def _generate_explanation(self, vms: List[Dict], placement: Dict[int, str], 
                             workers_state: Dict, fitness: float) -> str:
        """Generate human-readable explanation of placement decision"""
        lines = [
            f"\n{'='*70}",
            f"VM PLACEMENT DECISION - {self.availability_zone.upper()} CLUSTER",
            f"{'='*70}",
            f"Algorithm: Genetic Algorithm with Welford Statistics",
            f"Fitness Score: {fitness:.2f}",
            f"Barrier Penalty (Γ): {self.GAMMA:.0f}",
            f"Confidence Factor (K): CPU={self.K_cpu}, RAM={self.K_ram}",
            f"",
            f"PLACEMENT RESULT:",
        ]
        
        # Group VMs by worker
        worker_vms = {}
        for vm_id, worker_ip in placement.items():
            if worker_ip not in worker_vms:
                worker_vms[worker_ip] = []
            worker_vms[worker_ip].append(vm_id)
        
        for worker_ip, vm_ids in worker_vms.items():
            state = workers_state[worker_ip]
            capacity = state['capacity']
            usage = state['usage']
            
            lines.append(f"  Worker {worker_ip}:")
            lines.append(f"    VMs assigned: {vm_ids}")
            lines.append(f"    Capacity: {capacity['cores']} cores, {capacity['ram_mb']:.0f} MB RAM, {capacity['disk_gb']:.1f} GB disk")
            lines.append(f"    Current usage: CPU μ={usage['cpu']['mean']:.2f} σ={usage['cpu']['std_dev']:.2f}, RAM μ={usage['ram']['mean']:.0f} MB σ={usage['ram']['std_dev']:.0f} MB")
            lines.append("")
        
        lines.append(f"{'='*70}\n")
        
        explanation = "\n".join(lines)
        logger.info(explanation)
        
        return explanation
