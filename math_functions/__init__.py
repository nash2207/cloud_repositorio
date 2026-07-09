"""
Pure Mathematical Functions Module

All functions in this module are:
- Pure (deterministic input → deterministic output)
- Zero I/O (no file/network/database operations)
- Stateless (no global state mutations)
- Testable in isolation (unit testable)

Submodules:
- welford_pure: Welford's algorithm for online statistics
- resource_calculator: Resource allocation and fitness calculations
- genetic_algorithm: Infrastructure-agnostic GA optimization
"""

from .welford_pure import (
    welford_update,
    welford_get_variance,
    welford_get_std_dev,
    welford_combine_variances,
    welford_combine_std_dev
)

from .resource_calculator import (
    calculate_confidence_bound,
    calculate_clt_confidence_sum,
    calculate_dimensionless_delta,
    calculate_dimensionless_rho,
    calculate_weighted_penalty,
    calculate_weighted_imbalance,
    calculate_fitness,
    calculate_gamma_barrier
)

from .genetic_algorithm import (
    initialize_population,
    evaluate_population,
    tournament_selection,
    select_population,
    single_point_crossover,
    uniform_mutation,
    elitism_selection,
    genetic_algorithm
)

__all__ = [
    # Welford
    'welford_update',
    'welford_get_variance',
    'welford_get_std_dev',
    'welford_combine_variances',
    'welford_combine_std_dev',
    # Resource Calculator
    'calculate_confidence_bound',
    'calculate_clt_confidence_sum',
    'calculate_dimensionless_delta',
    'calculate_dimensionless_rho',
    'calculate_weighted_penalty',
    'calculate_weighted_imbalance',
    'calculate_fitness',
    'calculate_gamma_barrier',
    # Genetic Algorithm
    'initialize_population',
    'evaluate_population',
    'tournament_selection',
    'select_population',
    'single_point_crossover',
    'uniform_mutation',
    'elitism_selection',
    'genetic_algorithm',
]
