"""
Online Statistics using Welford's Algorithm
Computes mean (μ) and standard deviation (σ) in O(1) space
"""
import math


class OnlineStats:
    """
    Welford's online algorithm for computing mean and variance
    without storing all historical data points.
    
    Formulas:
        M_k = M_{k-1} + (x_k - M_{k-1}) / k
        S_k = S_{k-1} + (x_k - M_{k-1}) * (x_k - M_k)
        σ² = S_k / (k - 1)  for sample variance
        σ = sqrt(σ²)
    """
    
    def __init__(self):
        self.n = 0          # Count of samples
        self.mean = 0.0     # Running mean (μ)
        self.M2 = 0.0       # Sum of squared differences from mean
    
    def update(self, value):
        """
        Add a new sample and update statistics
        
        Args:
            value (float): New data point
        """
        self.n += 1
        delta = value - self.mean
        self.mean += delta / self.n
        delta2 = value - self.mean
        self.M2 += delta * delta2
    
    def get_mean(self):
        """Get current mean (μ)"""
        return self.mean if self.n > 0 else 0.0
    
    def get_variance(self):
        """Get sample variance (σ²)"""
        if self.n < 2:
            return 0.0
        return self.M2 / (self.n - 1)
    
    def get_stddev(self):
        """Get standard deviation (σ)"""
        return math.sqrt(self.get_variance())
    
    def get_stats(self):
        """Get all statistics as dict"""
        return {
            'n': self.n,
            'mean': self.get_mean(),
            'variance': self.get_variance(),
            'stddev': self.get_stddev()
        }
    
    def to_dict(self):
        """Serialize for database storage"""
        return {
            'n': self.n,
            'mean': self.mean,
            'M2': self.M2
        }
    
    @classmethod
    def from_dict(cls, data):
        """Deserialize from database"""
        stats = cls()
        stats.n = data.get('n', 0)
        stats.mean = data.get('mean', 0.0)
        stats.M2 = data.get('M2', 0.0)
        return stats
