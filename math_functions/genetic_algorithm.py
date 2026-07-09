"""
Pure Genetic Algorithm implementation
Infrastructure-agnostic optimization engine
Zero I/O, accepts fitness function as callback
"""
import random
from typing import List, Tuple, Callable, Optional
import logging

logger = logging.getLogger(__name__)


# Type alias for chromosome (solution encoding)
Chromosome = List[int]
FitnessFunction = Callable[[Chromosome], float]


def initialize_population(population_size: int, chromosome_length: int, 
                         gene_range: Tuple[int, int]) -> List[Chromosome]:
    """
    Create initial random population
    
    Pure function: Generates random chromosomes
    
    Args:
        population_size: Number of individuals in population
        chromosome_length: Length of each chromosome (number of VMs)
        gene_range: (min_value, max_value) for each gene (worker indices)
    
    Returns:
        List[Chromosome]: Initial population
    
    Encoding:
        Each chromosome = [worker_idx_vm1, worker_idx_vm2, ...]
        Example: [0, 2, 1] means VM1→Worker0, VM2→Worker2, VM3→Worker1
    """
    population = []
    min_gene, max_gene = gene_range
    
    for _ in range(population_size):
        chromosome = [random.randint(min_gene, max_gene) for _ in range(chromosome_length)]
        population.append(chromosome)
    
    return population


def evaluate_population(population: List[Chromosome], 
                       fitness_func: FitnessFunction) -> List[float]:
    """
    Evaluate fitness for all individuals
    
    Pure function: Maps population through fitness function
    
    Args:
        population: List of chromosomes
        fitness_func: Callback function that evaluates a single chromosome
    
    Returns:
        List[float]: Fitness scores (same order as population)
    """
    return [fitness_func(chromosome) for chromosome in population]


def tournament_selection(population: List[Chromosome], 
                        fitness_scores: List[float],
                        tournament_size: int = 3) -> Chromosome:
    """
    Select one individual using tournament selection
    
    Pure function (with randomness): Probabilistic selection
    
    Args:
        population: List of chromosomes
        fitness_scores: Fitness scores for population
        tournament_size: Number of individuals in tournament
    
    Returns:
        Chromosome: Selected individual (copy)
    
    Algorithm:
        1. Randomly sample tournament_size individuals
        2. Return the one with highest fitness
    """
    tournament_indices = random.sample(range(len(population)), tournament_size)
    best_idx = max(tournament_indices, key=lambda i: fitness_scores[i])
    return population[best_idx].copy()


def select_population(population: List[Chromosome],
                     fitness_scores: List[float],
                     selection_size: int,
                     tournament_size: int = 3) -> List[Chromosome]:
    """
    Select multiple individuals using tournament selection
    
    Pure function (with randomness): Repeated selection
    
    Args:
        population: List of chromosomes
        fitness_scores: Fitness scores for population
        selection_size: Number of individuals to select
        tournament_size: Tournament size
    
    Returns:
        List[Chromosome]: Selected individuals
    """
    selected = []
    for _ in range(selection_size):
        individual = tournament_selection(population, fitness_scores, tournament_size)
        selected.append(individual)
    
    return selected


def single_point_crossover(parent1: Chromosome, parent2: Chromosome) -> Tuple[Chromosome, Chromosome]:
    """
    Perform single-point crossover
    
    Pure function (with randomness): Genetic recombination
    
    Args:
        parent1: First parent chromosome
        parent2: Second parent chromosome
    
    Returns:
        Tuple[Chromosome, Chromosome]: Two offspring
    
    Algorithm:
        1. Choose random crossover point
        2. child1 = parent1[:point] + parent2[point:]
        3. child2 = parent2[:point] + parent1[point:]
    """
    if len(parent1) <= 1:
        return parent1.copy(), parent2.copy()
    
    point = random.randint(1, len(parent1) - 1)
    child1 = parent1[:point] + parent2[point:]
    child2 = parent2[:point] + parent1[point:]
    
    return child1, child2


def uniform_mutation(chromosome: Chromosome, 
                    gene_range: Tuple[int, int],
                    mutation_rate: float) -> Chromosome:
    """
    Perform uniform random mutation
    
    Pure function (with randomness): Random gene replacement
    
    Args:
        chromosome: Chromosome to mutate
        gene_range: (min_value, max_value) for genes
        mutation_rate: Probability of mutating each gene
    
    Returns:
        Chromosome: Mutated chromosome
    
    Algorithm:
        For each gene, with probability mutation_rate, replace with random value
    """
    mutated = chromosome.copy()
    min_gene, max_gene = gene_range
    
    for i in range(len(mutated)):
        if random.random() < mutation_rate:
            mutated[i] = random.randint(min_gene, max_gene)
    
    return mutated


def elitism_selection(population: List[Chromosome],
                     fitness_scores: List[float],
                     elite_size: int) -> List[Chromosome]:
    """
    Select top elite individuals
    
    Pure function: Deterministic best selection
    
    Args:
        population: List of chromosomes
        fitness_scores: Fitness scores for population
        elite_size: Number of elite individuals to preserve
    
    Returns:
        List[Chromosome]: Elite individuals
    
    Purpose:
        Preserve best solutions across generations
    """
    elite_indices = sorted(
        range(len(fitness_scores)),
        key=lambda i: fitness_scores[i],
        reverse=True
    )[:elite_size]
    
    return [population[i].copy() for i in elite_indices]


def genetic_algorithm(
    chromosome_length: int,
    gene_range: Tuple[int, int],
    fitness_func: FitnessFunction,
    population_size: int = 50,
    generations: int = 100,
    mutation_rate: float = 0.15,
    elite_size: int = 5,
    tournament_size: int = 3,
    early_stop_threshold: Optional[float] = None,
    early_stop_generations: int = 20
) -> Tuple[Chromosome, float, List[float]]:
    """
    Run complete Genetic Algorithm
    
    Main GA loop controller - orchestrates pure functions
    
    Args:
        chromosome_length: Number of genes (VMs to place)
        gene_range: (min_worker_idx, max_worker_idx)
        fitness_func: BLACK-BOX fitness evaluation callback
        population_size: Number of individuals per generation
        generations: Maximum number of generations
        mutation_rate: Probability of gene mutation
        elite_size: Number of elite individuals to preserve
        tournament_size: Tournament size for selection
        early_stop_threshold: Fitness threshold for early stopping (optional)
        early_stop_generations: Generations without improvement before stopping
    
    Returns:
        Tuple[Chromosome, float, List[float]]:
            - Best solution found
            - Best fitness score
            - Fitness history (best fitness per generation)
    
    Algorithm:
        1. Initialize random population
        2. For each generation:
            a. Evaluate fitness
            b. Select elite
            c. Tournament selection
            d. Crossover
            e. Mutation
            f. Form new generation
        3. Return best solution
    
    Note:
        The GA knows NOTHING about infrastructure. It only:
        - Optimizes integer arrays
        - Calls fitness_func as black box
        - Maximizes fitness score
    """
    logger.info(f"Starting GA: pop={population_size}, gen={generations}, mut={mutation_rate}")
    
    # Initialize population
    population = initialize_population(population_size, chromosome_length, gene_range)
    
    best_solution = None
    best_fitness = float('-inf')
    fitness_history = []
    generations_without_improvement = 0
    
    for generation in range(generations):
        # Evaluate fitness
        fitness_scores = evaluate_population(population, fitness_func)
        
        # Track best solution
        gen_best_idx = max(range(len(fitness_scores)), key=lambda i: fitness_scores[i])
        gen_best_fitness = fitness_scores[gen_best_idx]
        fitness_history.append(gen_best_fitness)
        
        if gen_best_fitness > best_fitness:
            best_fitness = gen_best_fitness
            best_solution = population[gen_best_idx].copy()
            generations_without_improvement = 0
        else:
            generations_without_improvement += 1
        
        # Logging
        if generation % 20 == 0 or generation == generations - 1:
            logger.debug(f"Generation {generation}: best_fitness={gen_best_fitness:.2f}")
        
        # Early stopping
        if early_stop_threshold is not None and best_fitness >= early_stop_threshold:
            logger.info(f"Early stop: fitness threshold reached at generation {generation}")
            break
        
        if generations_without_improvement >= early_stop_generations:
            logger.info(f"Early stop: no improvement for {early_stop_generations} generations")
            break
        
        # Last generation - no need to create next population
        if generation == generations - 1:
            break
        
        # Selection
        selected = select_population(population, fitness_scores, population_size, tournament_size)
        
        # Crossover and Mutation
        offspring = []
        for i in range(0, len(selected) - 1, 2):
            parent1 = selected[i]
            parent2 = selected[i + 1]
            
            child1, child2 = single_point_crossover(parent1, parent2)
            child1 = uniform_mutation(child1, gene_range, mutation_rate)
            child2 = uniform_mutation(child2, gene_range, mutation_rate)
            
            offspring.append(child1)
            offspring.append(child2)
        
        # Elitism
        elite = elitism_selection(population, fitness_scores, elite_size)
        
        # New generation
        population = elite + offspring[:population_size - len(elite)]
    
    logger.info(f"GA completed: best_fitness={best_fitness:.2f}, generations={len(fitness_history)}")
    
    return best_solution, best_fitness, fitness_history
