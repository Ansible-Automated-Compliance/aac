#!/usr/bin/env python3
"""
Policy Validation Script for OPA CIS/NIST Compliance Libraries

This script validates that our Rego policies correctly implement the official
CIS benchmarks and NIST standards by checking policy logic, syntax, and 
compliance with expected behaviors.
"""

import json
import subprocess
import sys
import os
from pathlib import Path
from typing import Dict, List, Tuple, Any
import yaml
import argparse

class PolicyValidator:
    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root)
        self.policies_dir = self.repo_root / "policies"
        self.tests_dir = self.repo_root / "tests"
        self.errors = []
        self.warnings = []
        
    def run_opa_test(self, test_file: str) -> Tuple[bool, str]:
        """Run OPA test command and return result"""
        try:
            cmd = ["opa", "test", str(self.policies_dir), test_file]
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.repo_root)
            return result.returncode == 0, result.stdout + result.stderr
        except FileNotFoundError:
            return False, "OPA binary not found. Please install OPA first."
    
    def validate_rego_syntax(self, policy_file: Path) -> bool:
        """Validate Rego syntax using OPA fmt"""
        try:
            cmd = ["opa", "fmt", "--diff", str(policy_file)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.errors.append(f"Syntax error in {policy_file}: {result.stderr}")
                return False
            if result.stdout.strip():
                self.warnings.append(f"Formatting issues in {policy_file}")
            return True
        except FileNotFoundError:
            self.errors.append("OPA binary not found for syntax validation")
            return False
    
    def validate_package_structure(self, policy_file: Path) -> bool:
        """Validate that package names follow our conventions"""
        try:
            with open(policy_file, 'r') as f:
                content = f.read()
            
            # Extract package declaration
            package_lines = [line for line in content.split('\n') if line.strip().startswith('package ')]
            if not package_lines:
                self.errors.append(f"No package declaration found in {policy_file}")
                return False
            
            package_name = package_lines[0].split('package ')[1].strip()
            expected_prefixes = [
                'cis', 'nist', 'tests', 'nerc_cip', 'fisma', 'sox', 'soc2',
                'pci_dss', 'iso27001', 'corporate', 'stig', 'performance_tests'
            ]

            if not any(package_name.startswith(prefix) for prefix in expected_prefixes):
                self.errors.append(f"Invalid package name '{package_name}' in {policy_file}")
                return False
            
            return True
        except Exception as e:
            self.errors.append(f"Error validating package structure in {policy_file}: {e}")
            return False
    
    def validate_cis_policy_completeness(self) -> bool:
        """Validate that CIS policies cover expected controls"""
        cis_categories = [
            "cloud_providers", "operating_systems", "devsecops_tools", 
            "mobile_devices", "network_devices", "server_software",
            "desktop_software", "disa_stig"
        ]
        
        missing_categories = []
        for category in cis_categories:
            category_path = self.policies_dir / "cis" / category
            if not category_path.exists():
                missing_categories.append(category)
        
        if missing_categories:
            self.warnings.append(f"Missing CIS categories: {missing_categories}")
        
        return len(missing_categories) == 0
    
    def validate_nist_policy_completeness(self) -> bool:
        """Validate that NIST policies cover expected frameworks"""
        nist_frameworks = [
            "cybersecurity_framework_2.0",
            "sp_800_53",
            "sp_800_171", 
            "risk_management_framework"
        ]
        
        missing_frameworks = []
        for framework in nist_frameworks:
            framework_path = self.policies_dir / "nist" / framework
            if not framework_path.exists():
                missing_frameworks.append(framework)
        
        if missing_frameworks:
            self.warnings.append(f"Missing NIST frameworks: {missing_frameworks}")
        
        return len(missing_frameworks) == 0
    
    def validate_test_coverage(self) -> bool:
        """Validate that all policies have corresponding tests"""
        policy_files = list(self.policies_dir.rglob("*.rego"))
        test_files = list(self.tests_dir.rglob("*.rego"))
        
        # Extract package names from policy files
        policy_packages = set()
        for policy_file in policy_files:
            try:
                with open(policy_file, 'r') as f:
                    content = f.read()
                package_lines = [line for line in content.split('\n') if line.strip().startswith('package ')]
                if package_lines:
                    package_name = package_lines[0].split('package ')[1].strip()
                    if not package_name.startswith('tests'):
                        policy_packages.add(package_name)
            except Exception:
                continue
        
        # Extract imported packages from test files
        tested_packages = set()
        for test_file in test_files:
            try:
                with open(test_file, 'r') as f:
                    content = f.read()
                import_lines = [line for line in content.split('\n') if 'import data.' in line]
                for line in import_lines:
                    if 'import data.' in line:
                        imported = line.split('import data.')[1].split(' ')[0].strip()
                        tested_packages.add(imported)
            except Exception:
                continue
        
        untested_packages = policy_packages - tested_packages
        if untested_packages:
            self.warnings.append(f"Policies without tests: {list(untested_packages)}")
        
        return len(untested_packages) == 0
    
    def validate_input_schema_consistency(self) -> bool:
        """Validate that input schemas are consistent across related policies"""
        schema_patterns = {}
        policy_files = list(self.policies_dir.rglob("*.rego"))
        
        for policy_file in policy_files:
            try:
                with open(policy_file, 'r') as f:
                    content = f.read()
                
                # Extract input field references
                input_fields = []
                for line in content.split('\n'):
                    if 'input.' in line and not line.strip().startswith('#'):
                        fields = [part for part in line.split() if 'input.' in part]
                        input_fields.extend(fields)
                
                if input_fields:
                    # Group by policy type
                    if 'cis' in str(policy_file):
                        policy_type = 'cis'
                    elif 'nist' in str(policy_file):
                        policy_type = 'nist'
                    else:
                        continue
                    
                    if policy_type not in schema_patterns:
                        schema_patterns[policy_type] = set()
                    schema_patterns[policy_type].update(input_fields)
            
            except Exception:
                continue
        
        # Check for common patterns within each type
        for policy_type, fields in schema_patterns.items():
            common_fields = [f for f in fields if f.count('.') <= 2]  # Top-level fields
            if len(common_fields) > 50:  # Arbitrary threshold
                self.warnings.append(f"Many different input fields in {policy_type} policies - consider schema standardization")
        
        return True
    
    def validate_ansible_integration(self) -> bool:
        """Validate that policies can work with Ansible gather_facts output"""
        # Look for the canonical assessment playbook; fall back to any playbook in ansible/playbooks/
        ansible_file = self.repo_root / "ansible" / "playbooks" / "cis_rhel9_assessment.yml"
        if not ansible_file.exists():
            playbooks_dir = self.repo_root / "ansible" / "playbooks"
            candidates = list(playbooks_dir.glob("*.yml")) if playbooks_dir.exists() else []
            if not candidates:
                self.warnings.append("Ansible integration file not found")
                return False
            ansible_file = candidates[0]
        
        try:
            with open(ansible_file, 'r') as f:
                ansible_content = yaml.safe_load(f)
            
            # Check for gather_facts usage
            playbooks = ansible_content if isinstance(ansible_content, list) else [ansible_content]
            has_gather_facts = False
            
            for playbook in playbooks:
                if isinstance(playbook, dict) and playbook.get('gather_facts', True):
                    has_gather_facts = True
                    break
            
            if not has_gather_facts:
                self.warnings.append("Ansible playbook doesn't enable gather_facts")
                return False
            
            return True
        except Exception as e:
            self.errors.append(f"Error validating Ansible integration: {e}")
            return False
    
    def run_comprehensive_tests(self) -> bool:
        """Run the comprehensive test suite"""
        test_file = self.tests_dir / "comprehensive_test_suite.rego"
        if not test_file.exists():
            self.errors.append("Comprehensive test suite not found")
            return False
        
        success, output = self.run_opa_test(str(test_file))
        if not success:
            self.errors.append(f"Comprehensive tests failed: {output}")
            return False
        
        return True
    
    def validate_policy_documentation(self) -> bool:
        """Validate that policies have proper documentation"""
        policy_files = list(self.policies_dir.rglob("*.rego"))
        poorly_documented = []
        
        for policy_file in policy_files:
            try:
                with open(policy_file, 'r') as f:
                    content = f.read()
                
                # Count comment lines
                lines = content.split('\n')
                comment_lines = [line for line in lines if line.strip().startswith('#')]
                code_lines = [line for line in lines if line.strip() and not line.strip().startswith('#')]
                
                if len(code_lines) > 0:
                    comment_ratio = len(comment_lines) / len(code_lines)
                    if comment_ratio < 0.1:  # Less than 10% comments
                        poorly_documented.append(str(policy_file))
            
            except Exception:
                continue
        
        if poorly_documented:
            self.warnings.append(f"Policies with insufficient documentation: {poorly_documented[:5]}")  # Show first 5
        
        return len(poorly_documented) == 0
    
    def generate_validation_report(self) -> Dict[str, Any]:
        """Generate a comprehensive validation report"""
        report = {
            "validation_timestamp": subprocess.check_output(["date"]).decode().strip(),
            "repo_root": str(self.repo_root),
            "summary": {
                "total_errors": len(self.errors),
                "total_warnings": len(self.warnings),
                "validation_passed": len(self.errors) == 0
            },
            "errors": self.errors,
            "warnings": self.warnings,
            "policy_stats": self._get_policy_stats(),
            "test_stats": self._get_test_stats()
        }
        return report
    
    def _get_policy_stats(self) -> Dict[str, int]:
        """Get statistics about policy files"""
        stats = {
            "total_policy_files": len(list(self.policies_dir.rglob("*.rego"))),
            "cis_policy_files": len(list((self.policies_dir / "cis").rglob("*.rego"))) if (self.policies_dir / "cis").exists() else 0,
            "nist_policy_files": len(list((self.policies_dir / "nist").rglob("*.rego"))) if (self.policies_dir / "nist").exists() else 0
        }
        return stats
    
    def _get_test_stats(self) -> Dict[str, int]:
        """Get statistics about test files"""
        stats = {
            "total_test_files": len(list(self.tests_dir.rglob("*.rego"))) if self.tests_dir.exists() else 0,
            "total_test_functions": 0
        }
        
        if self.tests_dir.exists():
            for test_file in self.tests_dir.rglob("*.rego"):
                try:
                    with open(test_file, 'r') as f:
                        content = f.read()
                    test_functions = [line for line in content.split('\n') if line.strip().startswith('test_')]
                    stats["total_test_functions"] += len(test_functions)
                except Exception:
                    continue
        
        return stats

def main():
    parser = argparse.ArgumentParser(description="Validate OPA CIS/NIST compliance policies")
    parser.add_argument("--repo-root", default=".", help="Repository root directory")
    parser.add_argument("--output", help="Output file for validation report (JSON)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--check-syntax", action="store_true", help="Only check Rego syntax")
    parser.add_argument("--check-tests", action="store_true", help="Only run tests")
    
    args = parser.parse_args()
    
    validator = PolicyValidator(args.repo_root)
    
    print("🔍 Starting policy validation...")
    
    if args.check_syntax:
        print("📝 Validating Rego syntax...")
        policy_files = list(validator.policies_dir.rglob("*.rego"))
        for policy_file in policy_files:
            validator.validate_rego_syntax(policy_file)
    elif args.check_tests:
        print("🧪 Running comprehensive tests...")
        validator.run_comprehensive_tests()
    else:
        # Full validation
        validations = [
            ("📝 Validating Rego syntax", lambda: all(validator.validate_rego_syntax(f) for f in validator.policies_dir.rglob("*.rego"))),
            ("📦 Validating package structure", lambda: all(validator.validate_package_structure(f) for f in validator.policies_dir.rglob("*.rego"))),
            ("🏗️  Validating CIS policy completeness", validator.validate_cis_policy_completeness),
            ("🔐 Validating NIST policy completeness", validator.validate_nist_policy_completeness),
            ("🧪 Validating test coverage", validator.validate_test_coverage),
            ("📋 Validating input schema consistency", validator.validate_input_schema_consistency),
            ("⚙️  Validating Ansible integration", validator.validate_ansible_integration),
            ("🧪 Running comprehensive tests", validator.run_comprehensive_tests),
            ("📚 Validating policy documentation", validator.validate_policy_documentation)
        ]
        
        for description, validation_func in validations:
            print(f"{description}...")
            try:
                success = validation_func()
                if args.verbose:
                    status = "✅ PASS" if success else "⚠️  WARNINGS"
                    print(f"   {status}")
            except Exception as e:
                validator.errors.append(f"Validation error in {description}: {e}")
                if args.verbose:
                    print(f"   ❌ ERROR: {e}")
    
    # Generate report
    report = validator.generate_validation_report()
    
    # Output results
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"📄 Validation report saved to {args.output}")
    
    # Print summary
    print("\n" + "="*60)
    print("📊 VALIDATION SUMMARY")
    print("="*60)
    print(f"Total Errors: {report['summary']['total_errors']}")
    print(f"Total Warnings: {report['summary']['total_warnings']}")
    print(f"Policy Files: {report['policy_stats']['total_policy_files']}")
    print(f"Test Files: {report['test_stats']['total_test_files']}")
    print(f"Test Functions: {report['test_stats']['total_test_functions']}")
    
    if report['summary']['validation_passed']:
        print("✅ VALIDATION PASSED")
        return 0
    else:
        print("❌ VALIDATION FAILED")
        if validator.errors:
            print("\n🚨 ERRORS:")
            for error in validator.errors:
                print(f"  • {error}")
        if validator.warnings and args.verbose:
            print("\n⚠️  WARNINGS:")
            for warning in validator.warnings:
                print(f"  • {warning}")
        return 1

if __name__ == "__main__":
    sys.exit(main())