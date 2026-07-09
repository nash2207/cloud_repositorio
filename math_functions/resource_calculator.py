"""
Pure mathematical functions for resource calculations
Based on Central Limit Theorem and confidence intervals
Zero I/O, pure deterministic calculations
"""
import math
from typing import List, Dict


def calculate_confidence_bound(mean: float, std_dev: float, k: float) -> float:
    """
    Calculate confidence upper bound for resource usage
    
    Pure function: Deterministic calculation
    
    Args:
        mean: Mean usage (μ)
        std_dev: Standard deviation (σ)
        k: Confidence factor (1.645 for 90% one-sided)
    
    Returns:
        float: Upper confidence bound
    
    Formula:
        UCB = μ + K·σ
    
    Interpretation:
        With 90% confidence (K=1.645), actual usage will be below UCB
    """
    return mean + k * std_dev


def calculate_clt_confidence_sum(means: List[float], std_devs: List[float], k: float) -> float:
    """
    Calculate confidence bound for sum of independent variables using CLT
    
    Pure function: Central Limit Theorem application
    
    Args:
        means: List of mean values
        std_devs: List of standard deviations
        k: Confidence factor
    
    Returns:
        float: Confidence upper bound for sum
    
    Formula:
        Sum_μ = Σμ_i
        Sum_σ = √(Σσ²_i)  [Central Limit Theorem]
        UCB = Sum_μ + K·Sum_σ
    """
    sum_mean = sum(means)
    sum_variance = sum(s**2 for s in std_devs)
    sum_std_dev = math.sqrt(sum_variance)
    
    return calculate_confidence_bound(sum_mean, sum_std_dev, k)


def calculate_dimensionless_delta(allocated: float, capacity: float) -> float:
    """
    Calculate dimensionless relative overload (Δ)
    
    Pure function: Overflow penalty calculation
    
    Args:
        allocated: Allocated/used resource amount
        capacity: Total capacity
    
    Returns:
        float: Relative overload (0 if within capacity, >0 if overloaded)
    
    Formula:
        Δ = max(0, (allocated - capacity) / capacity)
    
    Interpretation:
        Δ = 0.00 → Within capacity
        Δ = 0.05 → 5% overload
        Δ = 0.10 → 10% overload
    """
    if capacity <= 0:
        return float('inf') if allocated > 0 else 0.0
    
    overload = max(0, allocated - capacity)
    return overload / capacity


def calculate_dimensionless_rho(allocated: float, capacity: float) -> float:
    """
    Calculate dimensionless relative utilization (ρ)
    
    Pure function: Utilization ratio calculation
    
    Args:
        allocated: Allocated/used resource amount
        capacity: Total capacity
    
    Returns:
        float: Relative utilization (0.0 to 1.0+)
    
    Formula:
        ρ = allocated / capacity
    
    Interpretation:
        ρ = 0.50 → 50% utilized
        ρ = 0.80 → 80% utilized
        ρ = 1.00 → Fully utilized
    """
    if capacity <= 0:
        return float('inf') if allocated > 0 else 0.0
    
    return allocated / capacity


def calculate_weighted_penalty(deltas: Dict[str, float], weights: Dict[str, float]) -> float:
    """
    Calculate weighted quadratic penalty term
    
    Pure function: Weighted sum of squared deltas
    
    Args:
        deltas: Dict of dimensionless overloads {resource: Δ}
        weights: Dict of resource weights {resource: w}
    
    Returns:
        float: Weighted penalty
    
    Formula:
        Penalty = Σ(w_c · Δ²)
    
    Purpose:
        Quadratic penalty heavily penalizes oversubscription
    """
    penalty = 0.0
    for resource, delta in deltas.items():
        weight = weights.get(resource, 0.0)
        penalty += weight * (delta ** 2)
    
    return penalty


def calculate_weighted_imbalance(rhos: Dict[str, float], weights: Dict[str, float]) -> float:
    """
    Calculate weighted quadratic imbalance term
    
    Pure function: Weighted sum of squared utilizations
    
    Args:
        rhos: Dict of dimensionless utilizations {resource: ρ}
        weights: Dict of resource weights {resource: w}
    
    Returns:
        float: Weighted imbalance
    
    Formula:
        Imbalance = Σ(w_c · ρ²)
    
    Purpose:
        Encourages balanced load distribution across workers
    """
    imbalance = 0.0
    for resource, rho in rhos.items():
        weight = weights.get(resource, 0.0)
        imbalance += weight * (rho ** 2)
    
    return imbalance


def calculate_fitness(total_penalty: float, total_imbalance: float, gamma: float) -> float:
    """
    Calculate master fitness function
    
    Pure function: Objective function evaluation
    
    Args:
        total_penalty: Total overload penalty across all workers
        total_imbalance: Total utilization imbalance across all workers
        gamma: Barrier penalty factor (Γ)
    
    Returns:
        float: Fitness score (higher is better)
    
    Formula:
        F(X) = -[Γ · Σ(w_c · Δ²)] - Σ(w_c · ρ²)
    
    Components:
        - First term: Hard constraint (capacity violations)
        - Second term: Soft constraint (load balancing)
        - Γ: Scales penalty relative to cluster size
    
    Reference:
        Custom formulation based on barrier method optimization
    """
    return -(gamma * total_penalty) - total_imbalance


def calculate_gamma_barrier(num_workers: int, w_min: float, epsilon: float) -> float:
    """
    Calculate barrier penalty factor (Γ) for a cluster
    
    Pure function: Dynamic penalty scaling
    
    Args:
        num_workers: Number of workers in cluster (N)
        w_min: Minimum resource weight
        epsilon: Violation tolerance (typically 0.01 for 1%)
    
    Returns:
        float: Barrier penalty factor (Γ)
    
    Formula:
        Γ = N / (w_min · ε²)
    
    Interpretation:
        Larger clusters → Higher Γ → Stronger penalty
        Smaller tolerance → Higher Γ → Stricter enforcement
    
    Example:
        N=3, w_min=0.20, ε=0.01 → Γ = 150,000
    """
    if w_min <= 0 or epsilon <= 0:
        raise ValueError("w_min and epsilon must be positive")
    
    return num_workers / (w_min * epsilon ** 2)
