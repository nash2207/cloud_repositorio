"""
Pure mathematical functions for Welford's Algorithm
Zero I/O, pure deterministic calculations
"""
from typing import Tuple


def welford_update(n: int, mean: float, M2: float, new_value: float) -> Tuple[int, float, float]:
    """
    Update Welford statistics with a new sample
    
    Pure function: Takes current state, returns new state
    
    Args:
        n: Current number of samples
        mean: Current mean (μ)
        M2: Current sum of squared differences
        new_value: New sample value
    
    Returns:
        Tuple[int, float, float]: (new_n, new_mean, new_M2)
    
    Algorithm:
        μ_n = μ_{n-1} + (x_n - μ_{n-1}) / n
        M2_n = M2_{n-1} + (x_n - μ_{n-1})(x_n - μ_n)
    
    Reference:
        Welford, B. P. (1962). "Note on a method for calculating corrected sums of squares and products"
    """
    new_n = n + 1
    delta = new_value - mean
    new_mean = mean + delta / new_n
    delta2 = new_value - new_mean
    new_M2 = M2 + delta * delta2
    
    return new_n, new_mean, new_M2


def welford_get_variance(n: int, M2: float) -> float:
    """
    Calculate variance from Welford state
    
    Pure function: Deterministic calculation
    
    Args:
        n: Number of samples
        M2: Sum of squared differences
    
    Returns:
        float: Variance (σ²)
    
    Formula:
        σ² = M2 / (n - 1)
    """
    if n < 2:
        return 0.0
    return M2 / (n - 1)


def welford_get_std_dev(n: int, M2: float) -> float:
    """
    Calculate standard deviation from Welford state
    
    Pure function: Deterministic calculation
    
    Args:
        n: Number of samples
        M2: Sum of squared differences
    
    Returns:
        float: Standard deviation (σ)
    
    Formula:
        σ = √(M2 / (n - 1))
    """
    variance = welford_get_variance(n, M2)
    return variance ** 0.5


def welford_combine_variances(variances: list[float]) -> float:
    """
    Combine variances of independent random variables
    
    Pure function: Sum of variances
    
    Args:
        variances: List of variance values
    
    Returns:
        float: Combined variance
    
    Formula:
        Var(X + Y) = Var(X) + Var(Y)  [for independent X, Y]
    """
    return sum(variances)


def welford_combine_std_dev(variances: list[float]) -> float:
    """
    Calculate standard deviation of sum of independent variables
    
    Pure function: Square root of sum of variances
    
    Args:
        variances: List of variance values
    
    Returns:
        float: Standard deviation of sum
    
    Formula:
        σ(X + Y) = √(Var(X) + Var(Y))
    """
    total_variance = welford_combine_variances(variances)
    return total_variance ** 0.5
