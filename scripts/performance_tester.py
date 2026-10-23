#!/usr/bin/env python3
"""
Performance Testing Tool for OPA Compliance Policies

This tool runs comprehensive performance tests on OPA policies to measure
execution time, memory usage, and scalability characteristics.
"""

import json
import subprocess
import time
import sys
import psutil
import statistics
from pathlib import Path
from typing import Dict, List, Any, Tuple
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import tempfile

class PerformanceTester:
    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root)
        self.policies_dir = self.repo_root / "policies"
        self.tests_dir = self.repo_root / "tests"
        self.results = []
        
    def measure_opa_execution(self, test_file: str, iterations: int = 5) -> Dict[str, Any]:
        """Measure OPA test execution performance"""
        execution_times = []
        memory_usage = []
        
        for i in range(iterations):
            # Start memory monitoring
            process = psutil.Process()
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            start_time = time.perf_counter()
            
            try:
                result = subprocess.run(
                    ["opa", "test", str(self.repo_root), test_file],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                end_time = time.perf_counter()
                execution_time = (end_time - start_time) * 1000  # Convert to milliseconds
                
                final_memory = process.memory_info().rss / 1024 / 1024  # MB
                memory_delta = final_memory - initial_memory
                
                if result.returncode == 0:
                    execution_times.append(execution_time)
                    memory_usage.append(memory_delta)
                else:
                    print(f"⚠️  Test failed on iteration {i+1}: {result.stderr}")
                    
            except subprocess.TimeoutExpired:
                print(f"⏰ Test timed out on iteration {i+1}")
                execution_times.append(60000)  # 60 seconds timeout
                memory_usage.append(0)
            except Exception as e:
                print(f"❌ Error on iteration {i+1}: {e}")
                continue
        
        if not execution_times:
            return {
                "test_file": test_file,
                "status": "failed",
                "error": "No successful executions"
            }
        
        return {
            "test_file": test_file,
            "status": "success",
            "iterations": len(execution_times),
            "execution_time_ms": {
                "min": min(execution_times),
                "max": max(execution_times),
                "mean": statistics.mean(execution_times),
                "median": statistics.median(execution_times),
                "stdev": statistics.stdev(execution_times) if len(execution_times) > 1 else 0
            },
            "memory_usage_mb": {
                "min": min(memory_usage) if memory_usage else 0,
                "max": max(memory_usage) if memory_usage else 0,
                "mean": statistics.mean(memory_usage) if memory_usage else 0
            }
        }
    
    def run_policy_compilation_benchmark(self) -> Dict[str, Any]:
        """Benchmark policy compilation time"""
        policy_files = list(self.policies_dir.rglob("*.rego"))
        test_files = list(self.tests_dir.rglob("*.rego"))
        
        start_time = time.perf_counter()
        
        try:
            result = subprocess.run(
                ["opa", "build", str(self.policies_dir), str(self.tests_dir)],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            end_time = time.perf_counter()
            compilation_time = (end_time - start_time) * 1000
            
            return {
                "status": "success" if result.returncode == 0 else "failed",
                "compilation_time_ms": compilation_time,
                "policy_files_count": len(policy_files),
                "test_files_count": len(test_files),
                "total_files": len(policy_files) + len(test_files),
                "files_per_second": (len(policy_files) + len(test_files)) / (compilation_time / 1000),
                "stdout": result.stdout,
                "stderr": result.stderr if result.returncode != 0 else ""
            }
            
        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "compilation_time_ms": 120000,
                "error": "Compilation timed out after 2 minutes"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
    
    def run_scalability_test(self) -> Dict[str, Any]:
        """Test scalability with different input sizes"""
        scalability_results = {}
        
        # Test different data sizes
        test_sizes = [10, 100, 1000, 5000]
        
        for size in test_sizes:
            # Generate test data of specific size
            test_data = {
                "loaded_modules": [f"module_{i}" for i in range(size)],
                "mounts": {
                    f"/mount{i}": {
                        "device": f"/dev/disk{i}",
                        "fstype": "ext4",
                        "options": ["rw", "nodev"]
                    } for i in range(min(size, 100))  # Limit mounts to avoid excessive memory
                }
            }
            
            # Create temporary test file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(test_data, f)
                temp_file = f.name
            
            try:
                # Test with cramfs_disabled policy (simple test)
                start_time = time.perf_counter()
                
                result = subprocess.run([
                    "opa", "eval", 
                    "-d", str(self.policies_dir),
                    "-i", temp_file,
                    "data.cis.filesystem.cramfs_disabled"
                ], capture_output=True, text=True, timeout=30)
                
                end_time = time.perf_counter()
                execution_time = (end_time - start_time) * 1000
                
                scalability_results[f"size_{size}"] = {
                    "input_size": size,
                    "execution_time_ms": execution_time,
                    "success": result.returncode == 0,
                    "throughput_items_per_ms": size / execution_time if execution_time > 0 else 0
                }
                
            except subprocess.TimeoutExpired:
                scalability_results[f"size_{size}"] = {
                    "input_size": size,
                    "execution_time_ms": 30000,
                    "success": False,
                    "error": "timeout"
                }
            except Exception as e:
                scalability_results[f"size_{size}"] = {
                    "input_size": size,
                    "success": False,
                    "error": str(e)
                }
            finally:
                # Clean up temporary file
                try:
                    Path(temp_file).unlink()
                except:
                    pass
        
        return scalability_results
    
    def run_concurrent_evaluation_test(self, num_threads: int = 4) -> Dict[str, Any]:
        """Test concurrent policy evaluations"""
        test_data = {
            "os_family": "RedHat",
            "selinux_status": "enforcing",
            "firewall_enabled": True,
            "ssh_port": 22
        }
        
        def evaluate_policy():
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(test_data, f)
                temp_file = f.name
            
            try:
                start_time = time.perf_counter()
                result = subprocess.run([
                    "opa", "eval",
                    "-d", str(self.policies_dir),
                    "-i", temp_file,
                    "data.cis.allow"
                ], capture_output=True, text=True, timeout=10)
                
                end_time = time.perf_counter()
                
                return {
                    "execution_time_ms": (end_time - start_time) * 1000,
                    "success": result.returncode == 0,
                    "result": result.stdout.strip() if result.returncode == 0 else result.stderr
                }
            except Exception as e:
                return {
                    "execution_time_ms": 0,
                    "success": False,
                    "error": str(e)
                }
            finally:
                try:
                    Path(temp_file).unlink()
                except:
                    pass
        
        # Run concurrent evaluations
        start_time = time.perf_counter()
        
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(evaluate_policy) for _ in range(num_threads * 3)]
            results = [future.result() for future in as_completed(futures)]
        
        end_time = time.perf_counter()
        total_time = (end_time - start_time) * 1000
        
        successful_results = [r for r in results if r.get("success", False)]
        execution_times = [r["execution_time_ms"] for r in successful_results]
        
        return {
            "total_evaluations": len(results),
            "successful_evaluations": len(successful_results),
            "total_time_ms": total_time,
            "concurrent_threads": num_threads,
            "average_execution_time_ms": statistics.mean(execution_times) if execution_times else 0,
            "throughput_evaluations_per_second": len(successful_results) / (total_time / 1000) if total_time > 0 else 0,
            "success_rate": len(successful_results) / len(results) * 100
        }
    
    def run_memory_stress_test(self) -> Dict[str, Any]:
        """Test memory usage under stress conditions"""
        # Generate large test data
        large_test_data = {
            "users": {
                f"user_{i}": {
                    "username": f"user{i}",
                    "role": f"role_{i % 10}",
                    "permissions": [f"perm_{j}" for j in range(20)]
                } for i in range(1000)
            },
            "systems": {
                f"system_{i}": {
                    "hostname": f"host{i}",
                    "ip": f"192.168.{i//256}.{i%256}",
                    "services": [f"service_{j}" for j in range(10)]
                } for i in range(500)
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(large_test_data, f)
            temp_file = f.name
        
        try:
            # Monitor memory before
            process = psutil.Process()
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            start_time = time.perf_counter()
            
            result = subprocess.run([
                "opa", "eval",
                "-d", str(self.policies_dir),
                "-i", temp_file,
                "data.cis.allow"
            ], capture_output=True, text=True, timeout=60)
            
            end_time = time.perf_counter()
            
            final_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            return {
                "execution_time_ms": (end_time - start_time) * 1000,
                "initial_memory_mb": initial_memory,
                "final_memory_mb": final_memory,
                "memory_delta_mb": final_memory - initial_memory,
                "data_size_kb": Path(temp_file).stat().st_size / 1024,
                "success": result.returncode == 0,
                "memory_efficiency_kb_per_mb": (Path(temp_file).stat().st_size / 1024) / max(final_memory - initial_memory, 1)
            }
            
        except subprocess.TimeoutExpired:
            return {
                "execution_time_ms": 60000,
                "success": False,
                "error": "Memory stress test timed out"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            try:
                Path(temp_file).unlink()
            except:
                pass
    
    def run_comprehensive_performance_suite(self) -> Dict[str, Any]:
        """Run all performance tests"""
        print("🏃 Starting comprehensive performance test suite...")
        
        suite_results = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "system_info": {
                "cpu_count": psutil.cpu_count(),
                "memory_total_gb": psutil.virtual_memory().total / (1024**3),
                "python_version": sys.version.split()[0]
            }
        }
        
        # 1. Policy compilation benchmark
        print("📦 Testing policy compilation performance...")
        suite_results["compilation_benchmark"] = self.run_policy_compilation_benchmark()
        
        # 2. Individual test file performance
        print("🧪 Testing individual test file performance...")
        test_files = list(self.tests_dir.glob("*.rego"))
        test_performance = {}
        
        for test_file in test_files[:5]:  # Limit to first 5 test files
            print(f"   Testing {test_file.name}...")
            test_performance[test_file.name] = self.measure_opa_execution(str(test_file))
        
        suite_results["test_file_performance"] = test_performance
        
        # 3. Scalability test
        print("📈 Testing scalability with different input sizes...")
        suite_results["scalability_test"] = self.run_scalability_test()
        
        # 4. Concurrent evaluation test
        print("🔄 Testing concurrent policy evaluations...")
        suite_results["concurrent_evaluation"] = self.run_concurrent_evaluation_test()
        
        # 5. Memory stress test
        print("🧠 Testing memory usage under stress...")
        suite_results["memory_stress_test"] = self.run_memory_stress_test()
        
        # 6. Performance summary
        suite_results["performance_summary"] = self._generate_performance_summary(suite_results)
        
        return suite_results
    
    def _generate_performance_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate performance summary and recommendations"""
        summary = {
            "overall_status": "unknown",
            "key_metrics": {},
            "performance_issues": [],
            "recommendations": []
        }
        
        # Analyze compilation performance
        compilation = results.get("compilation_benchmark", {})
        if compilation.get("status") == "success":
            compile_time = compilation.get("compilation_time_ms", 0)
            files_per_sec = compilation.get("files_per_second", 0)
            
            summary["key_metrics"]["compilation_time_ms"] = compile_time
            summary["key_metrics"]["files_per_second"] = files_per_sec
            
            if compile_time > 30000:  # 30 seconds
                summary["performance_issues"].append("Slow policy compilation (>30s)")
                summary["recommendations"].append("Consider reducing policy complexity or splitting into modules")
        
        # Analyze test performance
        test_perf = results.get("test_file_performance", {})
        slow_tests = []
        for test_name, test_data in test_perf.items():
            if test_data.get("status") == "success":
                mean_time = test_data.get("execution_time_ms", {}).get("mean", 0)
                if mean_time > 5000:  # 5 seconds
                    slow_tests.append(test_name)
        
        if slow_tests:
            summary["performance_issues"].append(f"Slow test execution: {', '.join(slow_tests)}")
            summary["recommendations"].append("Optimize slow test cases or reduce test data size")
        
        # Analyze scalability
        scalability = results.get("scalability_test", {})
        scalability_issues = []
        for size_key, size_data in scalability.items():
            if size_data.get("execution_time_ms", 0) > 10000:  # 10 seconds
                scalability_issues.append(size_key)
        
        if scalability_issues:
            summary["performance_issues"].append("Poor scalability with large inputs")
            summary["recommendations"].append("Implement input size limits or optimize algorithms")
        
        # Analyze memory usage
        memory_test = results.get("memory_stress_test", {})
        memory_delta = memory_test.get("memory_delta_mb", 0)
        if memory_delta > 500:  # 500 MB
            summary["performance_issues"].append("High memory usage during evaluation")
            summary["recommendations"].append("Optimize memory usage or implement streaming evaluation")
        
        # Overall status
        if len(summary["performance_issues"]) == 0:
            summary["overall_status"] = "excellent"
        elif len(summary["performance_issues"]) <= 2:
            summary["overall_status"] = "good"
        else:
            summary["overall_status"] = "needs_improvement"
        
        return summary

def main():
    parser = argparse.ArgumentParser(description="Run performance tests on OPA compliance policies")
    parser.add_argument("--repo-root", default=".", help="Repository root directory")
    parser.add_argument("--output", help="Output file for performance report (JSON)")
    parser.add_argument("--test-file", help="Run performance test on specific test file")
    parser.add_argument("--iterations", type=int, default=5, help="Number of iterations for each test")
    parser.add_argument("--threads", type=int, default=4, help="Number of threads for concurrent tests")
    parser.add_argument("--quick", action="store_true", help="Run quick performance tests only")
    
    args = parser.parse_args()
    
    tester = PerformanceTester(args.repo_root)
    
    if args.test_file:
        print(f"🏃 Running performance test on {args.test_file}...")
        result = tester.measure_opa_execution(args.test_file, args.iterations)
        print(json.dumps(result, indent=2))
    elif args.quick:
        print("⚡ Running quick performance tests...")
        results = {
            "compilation": tester.run_policy_compilation_benchmark(),
            "concurrent": tester.run_concurrent_evaluation_test(args.threads)
        }
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(results, f, indent=2)
        else:
            print(json.dumps(results, indent=2))
    else:
        results = tester.run_comprehensive_performance_suite()
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"📄 Performance report saved to {args.output}")
        
        # Print summary
        summary = results.get("performance_summary", {})
        print(f"\n📊 PERFORMANCE SUMMARY")
        print("=" * 50)
        print(f"Overall Status: {summary.get('overall_status', 'unknown').upper()}")
        
        key_metrics = summary.get("key_metrics", {})
        if key_metrics:
            print(f"Key Metrics:")
            for metric, value in key_metrics.items():
                print(f"  • {metric}: {value:.2f}")
        
        issues = summary.get("performance_issues", [])
        if issues:
            print(f"\n⚠️  Performance Issues:")
            for issue in issues:
                print(f"  • {issue}")
        
        recommendations = summary.get("recommendations", [])
        if recommendations:
            print(f"\n💡 Recommendations:")
            for rec in recommendations:
                print(f"  • {rec}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())