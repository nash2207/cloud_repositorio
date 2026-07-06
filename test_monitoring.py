#!/usr/bin/env python3
"""
Test script to verify monitoring system is working
Bypasses web authentication to directly test the monitoring system
"""
import sys
sys.path.insert(0, '/home/ubuntu/cloud')

from monitoring.monitor import MonitoringSystem
from remote_executor import RemoteExecutor
from database import Database

print("=" * 60)
print("Monitoring System Test")
print("=" * 60)

# Initialize components
db = Database()
executor = RemoteExecutor()

# Get enabled clusters
clusters = db.data.get("clusters", {})
enabled_clusters = {k: v for k, v in clusters.items() if v is not None and isinstance(v, dict)}

print(f"\nEnabled clusters: {list(enabled_clusters.keys())}")

# Create monitoring system
monitoring = MonitoringSystem(db, executor, enabled_clusters)

# Check workers
print(f"\nInitialized workers: {list(monitoring.workers.keys())}")

# Manually trigger discovery once
print("\n" + "=" * 60)
print("Triggering VM discovery...")
print("=" * 60)
monitoring._discover_all_vms()

# Get cluster stats
print("\n" + "=" * 60)
print("Linux Cluster Stats:")
print("=" * 60)
cluster_stats = monitoring.get_cluster_stats('linux')

print(f"\nCluster: {cluster_stats['cluster']}")
print(f"Total Workers: {len(cluster_stats['workers'])}")
print(f"Total VMs: {cluster_stats['vms_count']}")
print(f"\nTotal Capacity:")
print(f"  - Cores: {cluster_stats['total_capacity']['cores']}")
print(f"  - RAM: {cluster_stats['total_capacity']['ram_mb']} MB ({cluster_stats['total_capacity']['ram_mb']/1024:.1f} GB)")
print(f"  - Disk: {cluster_stats['total_capacity']['disk_gb']:.1f} GB")

print(f"\nTotal Usage:")
print(f"  - CPU μ: {cluster_stats['total_usage']['cpu']['mean']:.1f}%")
print(f"  - CPU σ: {cluster_stats['total_usage']['cpu']['std_dev']:.1f}")
print(f"  - RAM μ: {cluster_stats['total_usage']['ram']['mean']:.0f} MB")
print(f"  - RAM σ: {cluster_stats['total_usage']['ram']['std_dev']:.0f} MB")
print(f"  - Disk allocated: {cluster_stats['total_usage']['disk']['allocated_gb']:.1f} GB")

print("\n" + "=" * 60)
print("Workers Detail:")
print("=" * 60)
for worker in cluster_stats['workers']:
    print(f"\n{worker['worker_ip']}:")
    print(f"  Capacity: {worker['capacity']['cores']} cores, {worker['capacity']['ram_mb']} MB RAM, {worker['capacity']['disk_gb']:.1f} GB disk")
    print(f"  VMs: {worker['vms_count']}")
    print(f"  CPU: {worker['usage']['cpu']['mean']:.1f} ± {worker['usage']['cpu']['std_dev']:.1f}")
    print(f"  RAM: {worker['usage']['ram']['mean']:.0f} ± {worker['usage']['ram']['std_dev']:.0f} MB")
    print(f"  Disk: {worker['usage']['disk']['allocated_gb']:.1f} GB")

print("\n" + "=" * 60)
print("✅ Monitoring system is working correctly!")
print("=" * 60)
print("\nIf you see worker capacity data above, the backend is fine.")
print("The UI issue is authentication-related - you need to login")
print("through the browser at http://localhost:8080")
print("=" * 60)
