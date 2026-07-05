"""
Genetic Algorithm for VM Placement
Uses Welford statistics (μ and σ) for probabilistic resource allocation
Implements oversubscription model with stochastic confidence intervals
"""
import logging
import random
import math
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)


class VMPlacementGA:
    """
    Genetic Algorithm for optimal VM placement
    Based on Central Limit Theorem and Welford's online statistics
    """
    
    # Resource weights (must sum to 1.0)
    W_RAM = 0.50  # RAM is incompressible (OOM Killer)
    W_CPU = 0.30  # CPU is compressible (Latency)
    W_DISK = 0.20  # Disk is static
    
    def __init__(self, monitoring_system, cluster_config, availability_zone):
        """
        Initialize GA for VM placement
        
        Args:
            monitoring_system: MonitoringSystem instance with Welford stats
            cluster_config: Cluster configuration dict
            availability_zone: "linux" or "openstack"
        """
        self.monitoring = monitoring_system
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
        
        # Barrier penalty factor Γ (dynamic per cluster)
        # Γ = N / (w_min * ε²) where:
        #   N = number of workers in THIS cluster
        #   w_min = minimum resource weight (0.20 for disk)
        #   ε = 1% tolerance for violation
        N = len(self.workers)
        w_min = min(self.W_RAM, self.W_CPU, self.W_DISK)  # w_min = 0.20 (disk)
        epsilon = 0.01
        self.GAMMA = N / (w_min * epsilon ** 2)
        
        logger.info(
            f"GA initialized for {availability_zone} cluster:"
        )
        logger.info(f"  - Workers (N): {N}")
        logger.info(f"  - w_min (disk): {w_min}")
        logger.info(f"  - ε (tolerance): {epsilon}")
        logger.info(f"  - Γ (barrier penalty): {self.GAMMA:.0f}")
        logger.info(f"  - K_cpu (confidence): {self.K_cpu}")
        logger.info(f"  - K_ram (confidence): {self.K_ram}")
        logger.info(f"  - Formula: Γ = {N} / ({w_min} * {epsilon}²) = {self.GAMMA:.0f}")
    
    def calculate_placement(self, vms_to_place: List[Dict]) -> Tuple[Dict[int, str], str]:
        """
        Calculate optimal VM placement using Genetic Algorithm
        
        Args:
            vms_to_place: List of VM dicts with {vm_id, flavor}
        
        Returns:
            Tuple[Dict[int, str], str]: 
                - {vm_id: worker_ip, ...}
                - Explanation log of placement decision
        """
        if not vms_to_place:
            return {}, "No VMs to place"
        
        if not self.workers:
            return {}, f"No workers available in {self.availability_zone} cluster"
        
        logger.info(f"Starting GA placement for {len(vms_to_place)} VMs on {len(self.workers)} workers")
        
        # Get current worker states from monitoring system
        workers_state = self._get_workers_state()
        
        # Run genetic algorithm
        best_solution, best_fitness = self._run_ga(vms_to_place, workers_state)
        
        # Build placement map
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
    
    def _get_workers_state(self) -> Dict[str, Dict]:
        """
        Get current state of all workers from monitoring system
        
        Returns:
            Dict[worker_ip, {capacity, usage, vms_count}]
        """
        workers_state = {}
        
        for worker_ip in self.workers:
            stats = self.monitoring.get_worker_stats(worker_ip)
            if stats:
                workers_state[worker_ip] = stats
            else:
                # Worker not yet initialized in monitoring
                workers_state[worker_ip] = {
                    'worker_ip': worker_ip,
                    'capacity': {'cores': 4, 'ram_mb': 8000, 'disk_gb': 10},
                    'usage': {
                        'cpu': {'mean': 0, 'std_dev': 0},
                        'ram': {'mean': 0, 'std_dev': 0},
                        'disk': {'allocated_gb': 0}
                    },
                    'vms_count': 0
                }
                logger.warning(f"Worker {worker_ip} not in monitoring, using defaults")
        
        return workers_state
    
    def _run_ga(self, vms_to_place: List[Dict], workers_state: Dict) -> Tuple[List[int], float]:
        """
        Run Genetic Algorithm
        
        Returns:
            Tuple[List[int], float]: Best solution and its fitness
        """
        # Initialize population
        population = self._initialize_population(len(vms_to_place))
        
        best_solution = None
        best_fitness = float('-inf')
        
        for generation in range(self.generations):
            # Evaluate fitness for all individuals
            fitness_scores = [
                self._evaluate_fitness(individual, vms_to_place, workers_state)
                for individual in population
            ]
            
            # Track best solution
            gen_best_idx = max(range(len(fitness_scores)), key=lambda i: fitness_scores[i])
            gen_best_fitness = fitness_scores[gen_best_idx]
            
            if gen_best_fitness > best_fitness:
                best_fitness = gen_best_fitness
                best_solution = population[gen_best_idx].copy()
            
            if generation % 20 == 0:
                logger.debug(f"Generation {generation}: best_fitness={gen_best_fitness:.2f}")
            
            # Selection
            selected = self._selection(population, fitness_scores)
            
            # Crossover and Mutation
            offspring = []
            for i in range(0, len(selected) - 1, 2):
                parent1 = selected[i]
                parent2 = selected[i + 1]
                child1, child2 = self._crossover(parent1, parent2)
                offspring.append(self._mutate(child1, len(self.workers)))
                offspring.append(self._mutate(child2, len(self.workers)))
            
            # Elitism: keep best solutions
            elite_indices = sorted(
                range(len(fitness_scores)),
                key=lambda i: fitness_scores[i],
                reverse=True
            )[:self.elite_size]
            elite = [population[i] for i in elite_indices]
            
            # New generation
            population = elite + offspring[:self.population_size - len(elite)]
        
        return best_solution, best_fitness
    
    def _initialize_population(self, num_vms: int) -> List[List[int]]:
        """Create initial random population"""
        population = []
        for _ in range(self.population_size):
            individual = [random.randint(0, len(self.workers) - 1) for _ in range(num_vms)]
            population.append(individual)
        return population
    
    def _evaluate_fitness(self, solution: List[int], vms: List[Dict], workers_state: Dict) -> float:
        """
        Evaluate fitness using the master objective function
        
        F(X) = -[Γ * Σ(w_c * Δ²)] - Σ(w_c * ρ²)
        
        Where:
            Δ = Relative overload (penalized quadratically)
            ρ = Relative utilization (minimized for balance)
            Γ = Barrier penalty factor
        """
        # Build worker assignments
        worker_assignments = {worker_ip: [] for worker_ip in self.workers}
        for vm_idx, worker_idx in enumerate(solution):
            worker_ip = self.workers[worker_idx]
            worker_assignments[worker_ip].append(vms[vm_idx])
        
        total_penalty = 0.0
        total_imbalance = 0.0
        
        for worker_ip, assigned_vms in worker_assignments.items():
            worker_state = workers_state[worker_ip]
            capacity = worker_state['capacity']
            current_usage = worker_state['usage']
            
            # Calculate confidence intervals for new load
            new_load = self._calculate_load_with_confidence(
                assigned_vms, current_usage, capacity
            )
            
            # Calculate relative overload (Δ) for each resource
            delta_cpu = max(0, new_load['cpu'] - capacity['cores']) / capacity['cores']
            delta_ram = max(0, new_load['ram'] - capacity['ram_mb']) / capacity['ram_mb']
            delta_disk = max(0, new_load['disk'] - capacity['disk_gb']) / capacity['disk_gb']
            
            # Calculate relative utilization (ρ) for each resource
            rho_cpu = new_load['cpu'] / capacity['cores']
            rho_ram = new_load['ram'] / capacity['ram_mb']
            rho_disk = new_load['disk'] / capacity['disk_gb']
            
            # Penalty term (hard constraints)
            penalty = (
                self.W_CPU * (delta_cpu ** 2) +
                self.W_RAM * (delta_ram ** 2) +
                self.W_DISK * (delta_disk ** 2)
            )
            total_penalty += penalty
            
            # Imbalance term (soft constraints)
            imbalance = (
                self.W_CPU * (rho_cpu ** 2) +
                self.W_RAM * (rho_ram ** 2) +
                self.W_DISK * (rho_disk ** 2)
            )
            total_imbalance += imbalance
        
        # Master objective function
        fitness = -(self.GAMMA * total_penalty) - total_imbalance
        
        return fitness
    
    def _calculate_load_with_confidence(self, new_vms: List[Dict], 
                                       current_usage: Dict, 
                                       capacity: Dict) -> Dict:
        """
        Calculate expected load using Central Limit Theorem
        
        Confidence = Σμ + K * √(Σσ²)
        
        For disk (deterministic): simple sum
        """
        # Current load (mean + K * std_dev)
        current_cpu_confidence = (
            current_usage['cpu']['mean'] + 
            self.K_cpu * current_usage['cpu']['std_dev']
        )
        current_ram_confidence = (
            current_usage['ram']['mean'] + 
            self.K_ram * current_usage['ram']['std_dev']
        )
        current_disk = current_usage['disk']['allocated_gb']
        
        # New VMs load (assume default μ and σ for new VMs)
        # For ubuntu flavor: 1 core @ 0.5 vCPU mean, 0.5 GB RAM @ 256 MB mean
        new_cpu_mean = len(new_vms) * 0.5  # 50% CPU usage assumed
        new_cpu_variance = len(new_vms) * (0.15 ** 2)  # 15% std dev
        new_cpu_confidence = new_cpu_mean + self.K_cpu * math.sqrt(new_cpu_variance)
        
        new_ram_mean = len(new_vms) * 256  # 256 MB mean per VM
        new_ram_variance = len(new_vms) * (64 ** 2)  # 64 MB std dev
        new_ram_confidence = new_ram_mean + self.K_ram * math.sqrt(new_ram_variance)
        
        new_disk = len(new_vms) * 2.5  # 2.5 GB per VM (deterministic)
        
        return {
            'cpu': current_cpu_confidence + new_cpu_confidence,
            'ram': current_ram_confidence + new_ram_confidence,
            'disk': current_disk + new_disk
        }
    
    def _selection(self, population: List[List[int]], fitness_scores: List[float]) -> List[List[int]]:
        """Tournament selection"""
        selected = []
        tournament_size = 3
        
        for _ in range(len(population)):
            tournament = random.sample(list(zip(population, fitness_scores)), tournament_size)
            winner = max(tournament, key=lambda x: x[1])[0]
            selected.append(winner.copy())
        
        return selected
    
    def _crossover(self, parent1: List[int], parent2: List[int]) -> Tuple[List[int], List[int]]:
        """Single-point crossover"""
        if len(parent1) <= 1:
            return parent1.copy(), parent2.copy()
        
        point = random.randint(1, len(parent1) - 1)
        child1 = parent1[:point] + parent2[point:]
        child2 = parent2[:point] + parent1[point:]
        
        return child1, child2
    
    def _mutate(self, individual: List[int], num_workers: int) -> List[int]:
        """Random mutation"""
        mutated = individual.copy()
        for i in range(len(mutated)):
            if random.random() < self.mutation_rate:
                mutated[i] = random.randint(0, num_workers - 1)
        return mutated
    
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
