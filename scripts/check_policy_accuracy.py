#!/usr/bin/env python3
"""
Policy Accuracy Checker for CIS and NIST Standards

This script validates that our Rego policies accurately implement the official
CIS benchmarks and NIST framework requirements by cross-referencing with
standard definitions and expected control behaviors.
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Any, Tuple
import argparse

class PolicyAccuracyChecker:
    def __init__(self, repo_root: str, config_file: str = None):
        self.repo_root = Path(repo_root)
        self.policies_dir = self.repo_root / "policies"
        self.accuracy_issues = []
        
        # Load configuration from file or use defaults
        self.config = self._load_config(config_file) if config_file else self._get_default_config()
        
        self.cis_expected_controls = self.config.get("cis_expected_controls", {})
        self.nist_expected_functions = self.config.get("nist_expected_functions", {})
        self.security_thresholds = self.config.get("security_thresholds", {})
        self.custom_frameworks = self.config.get("custom_frameworks", {})
        
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration that can be extended"""
        return {
            "cis_expected_controls": {
                "linux": {
                    "filesystem": ["cramfs_disabled", "tmp_configured", "tmp_nodev", "tmp_nosuid", "tmp_noexec"],
                    "network": ["ip_forwarding_disabled", "packet_redirect_disabled", "secure_icmp"],
                    "access_control": ["ssh_root_login_disabled", "ssh_maxauthtries_limited", "ssh_protocol_2"],
                    "logging": ["rsyslog_configured", "log_file_permissions", "audit_configured"]
                },
                "windows": {
                    "access_control": ["local_logon_rights", "network_logon_rights", "password_policy"],
                    "audit": ["audit_policy_configured", "event_log_settings"],
                    "system": ["auto_update_enabled", "firewall_enabled"]
                },
                "kubernetes": {
                    "api_server": ["anonymous_auth_disabled", "audit_logs_enabled"],
                    "kubelet": ["read_only_port_disabled", "authorization_enabled"],
                    "etcd": ["client_cert_auth", "peer_cert_auth"]
                },
                "docker": {
                    "daemon": ["user_namespace_enabled", "content_trust_enabled"],
                    "containers": ["privileged_containers_restricted", "capabilities_dropped"]
                }
            },
            "nist_expected_functions": {
                "cybersecurity_framework_2.0": {
                    "govern": ["organizational_strategy", "risk_management", "supply_chain"],
                    "identify": ["asset_management", "risk_assessment", "governance"],
                    "protect": ["access_control", "awareness_training", "data_security"],
                    "detect": ["anomalies_events", "monitoring", "detection_processes"],
                    "respond": ["response_planning", "communications", "analysis"],
                    "recover": ["recovery_planning", "improvements", "communications"]
                },
                "sp_800_53": {
                    "access_control": ["account_management", "access_enforcement", "session_lock"],
                    "audit": ["audit_events", "audit_storage", "audit_review"],
                    "configuration": ["baseline_configuration", "change_control"],
                    "identification": ["user_identification", "device_identification"]
                },
                "sp_800_171": {
                    "access_control": ["authorized_access_only", "logon_attempt_limits"],
                    "audit": ["audit_events", "audit_review", "audit_reduction"],
                    "awareness_training": ["security_awareness", "rules_of_behavior"]
                },
                "risk_management_framework": {
                    "categorize": ["system_categorization", "high_water_mark"],
                    "select": ["control_selection", "tailoring"],
                    "implement": ["control_implementation", "documentation"],
                    "assess": ["control_assessment", "remediation"],
                    "authorize": ["authorization_decision", "plan_of_action"],
                    "monitor": ["continuous_monitoring", "ongoing_assessment"]
                }
            },
            "security_thresholds": {
                "session_timeout": 900,
                "max_auth_tries": 5,
                "password_min_length": 8,
                "account_lockout_duration": 15,
                "max_concurrent_sessions": 10,
                "password_max_age": 90,
                "audit_retention_days": 365
            },
            "custom_frameworks": {}
        }
    
    def _load_config(self, config_file: str) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            # Merge with defaults
            default_config = self._get_default_config()
            self._deep_merge(default_config, config)
            return default_config
        except Exception as e:
            print(f"Warning: Could not load config file {config_file}: {e}")
            return self._get_default_config()
    
    def _deep_merge(self, base: Dict, override: Dict) -> None:
        """Deep merge override dict into base dict"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
    
    def discover_policy_structure(self) -> Dict[str, Any]:
        """Dynamically discover the actual policy structure"""
        structure = {
            "frameworks": [],
            "categories": {},
            "total_policies": 0,
            "policy_files": []
        }
        
        if not self.policies_dir.exists():
            return structure
        
        # Discover top-level frameworks
        for item in self.policies_dir.iterdir():
            if item.is_dir():
                structure["frameworks"].append(item.name)
                structure["categories"][item.name] = self._discover_categories(item)
        
        # Count total policy files
        policy_files = list(self.policies_dir.rglob("*.rego"))
        structure["total_policies"] = len(policy_files)
        structure["policy_files"] = [str(f) for f in policy_files]
        
        return structure
    
    def _discover_categories(self, framework_path: Path) -> List[str]:
        """Discover categories within a framework"""
        categories = []
        for item in framework_path.rglob("*"):
            if item.is_dir():
                rel_path = item.relative_to(framework_path)
                categories.append(str(rel_path))
        return categories
    
    def check_cis_control_coverage(self) -> bool:
        """Check if CIS policies implement expected controls (dynamically discovers structure)"""
        missing_controls = []
        
        # Dynamically discover CIS structure
        cis_path = self.policies_dir / "cis"
        if not cis_path.exists():
            self.accuracy_issues.append("CIS policies directory not found")
            return False
        
        # Check all discovered frameworks and categories
        for framework_type, categories in self.cis_expected_controls.items():
            # Look for framework in multiple possible locations
            possible_paths = [
                cis_path / "operating_systems" / framework_type,
                cis_path / "cloud_providers" / framework_type,
                cis_path / "server_software" / framework_type,
                cis_path / framework_type
            ]
            
            framework_found = False
            for framework_path in possible_paths:
                if framework_path.exists():
                    framework_found = True
                    
                    for category, expected_controls in categories.items():
                        category_files = list(framework_path.rglob("*.rego"))
                        
                        # Read all policy content for this category
                        category_content = ""
                        for policy_file in category_files:
                            try:
                                with open(policy_file, 'r') as f:
                                    content = f.read()
                                    if category in str(policy_file) or category in content:
                                        category_content += content + "\n"
                            except Exception:
                                continue
                        
                        # Check for expected controls
                        for control in expected_controls:
                            if control not in category_content:
                                missing_controls.append(f"Missing {framework_type}/{category} control: {control}")
                    break
            
            if not framework_found:
                missing_controls.append(f"Framework not found: {framework_type}")
        
        if missing_controls:
            self.accuracy_issues.extend(missing_controls)
            return False
        return True
    
    def check_nist_function_coverage(self) -> bool:
        """Check if NIST policies implement expected functions"""
        missing_functions = []
        
        for framework, functions in self.nist_expected_functions.items():
            framework_path = self.policies_dir / "nist" / framework
            if not framework_path.exists():
                missing_functions.append(f"Missing NIST framework: {framework}")
                continue
            
            for function_name, expected_categories in functions.items():
                function_files = list(framework_path.rglob("*.rego"))
                
                # Read all policy content for this function
                function_content = ""
                for policy_file in function_files:
                    try:
                        with open(policy_file, 'r') as f:
                            content = f.read()
                            if function_name in str(policy_file) or function_name in content:
                                function_content += content + "\n"
                    except Exception:
                        continue
                
                # Check for expected categories
                for category in expected_categories:
                    if category not in function_content:
                        missing_functions.append(f"Missing {framework}/{function_name} category: {category}")
        
        if missing_functions:
            self.accuracy_issues.extend(missing_functions)
            return False
        return True
    
    def check_security_threshold_compliance(self) -> bool:
        """Check if policies enforce proper security thresholds"""
        threshold_violations = []
        policy_files = list(self.policies_dir.rglob("*.rego"))
        
        for policy_file in policy_files:
            try:
                with open(policy_file, 'r') as f:
                    content = f.read()
                
                # Check session timeout thresholds
                timeout_patterns = [
                    r'inactivity_timeout\s*<=?\s*(\d+)',
                    r'session_timeout\s*<=?\s*(\d+)',
                    r'timeout\s*<=?\s*(\d+)'
                ]
                
                for pattern in timeout_patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        timeout_val = int(match)
                        if timeout_val > self.security_thresholds["session_timeout"]:
                            threshold_violations.append(
                                f"{policy_file}: Session timeout {timeout_val} exceeds maximum {self.security_thresholds['session_timeout']}"
                            )
                
                # Check max authentication attempts
                auth_patterns = [
                    r'maximum_attempts\s*<=?\s*(\d+)',
                    r'max_attempts\s*<=?\s*(\d+)',
                    r'MaxAuthTries\s*(\d+)'
                ]
                
                for pattern in auth_patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        max_attempts = int(match)
                        if max_attempts > self.security_thresholds["max_auth_tries"]:
                            threshold_violations.append(
                                f"{policy_file}: Max auth attempts {max_attempts} exceeds maximum {self.security_thresholds['max_auth_tries']}"
                            )
                
                # Check account lockout duration
                lockout_patterns = [
                    r'lockout_duration\s*>=?\s*(\d+)',
                    r'lockout_time\s*>=?\s*(\d+)'
                ]
                
                for pattern in lockout_patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        lockout_duration = int(match)
                        if lockout_duration < self.security_thresholds["account_lockout_duration"]:
                            threshold_violations.append(
                                f"{policy_file}: Lockout duration {lockout_duration} below minimum {self.security_thresholds['account_lockout_duration']}"
                            )
            
            except Exception as e:
                threshold_violations.append(f"Error checking thresholds in {policy_file}: {e}")
        
        if threshold_violations:
            self.accuracy_issues.extend(threshold_violations)
            return False
        return True
    
    def check_policy_logic_consistency(self) -> bool:
        """Check for logical consistency in policy rules"""
        logic_issues = []
        policy_files = list(self.policies_dir.rglob("*.rego"))
        
        for policy_file in policy_files:
            try:
                with open(policy_file, 'r') as f:
                    content = f.read()
                
                # Check for contradictory boolean conditions
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    line = line.strip()
                    if '==' in line and 'true' in line and 'false' in line:
                        logic_issues.append(f"{policy_file}:{i+1}: Contradictory boolean condition")
                    
                    # Check for impossible numeric conditions
                    if '>=' in line and '<=' in line:
                        # Extract numbers to check for impossible ranges
                        numbers = re.findall(r'\d+', line)
                        if len(numbers) >= 2:
                            try:
                                num1, num2 = int(numbers[0]), int(numbers[1])
                                if '>=' in line.split('<=')[0] and num1 > num2:
                                    logic_issues.append(f"{policy_file}:{i+1}: Impossible numeric range")
                            except (ValueError, IndexError):
                                pass
                
                # Check for unreachable rules (rules that can never be true)
                rule_definitions = re.findall(r'^(\w+)\s*{', content, re.MULTILINE)
                for rule in rule_definitions:
                    rule_content = self._extract_rule_content(content, rule)
                    if rule_content and 'false' in rule_content and '==' in rule_content:
                        if rule_content.count('false') > rule_content.count('true'):
                            logic_issues.append(f"{policy_file}: Rule '{rule}' may be unreachable")
            
            except Exception as e:
                logic_issues.append(f"Error checking logic in {policy_file}: {e}")
        
        if logic_issues:
            self.accuracy_issues.extend(logic_issues)
            return False
        return True
    
    def _extract_rule_content(self, content: str, rule_name: str) -> str:
        """Extract the content of a specific rule"""
        pattern = rf'{rule_name}\s*{{([^}}]*)}}'
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1) if match else ""
    
    def check_input_field_consistency(self) -> bool:
        """Check that input field usage is consistent across related policies"""
        field_usage = {}
        policy_files = list(self.policies_dir.rglob("*.rego"))
        
        for policy_file in policy_files:
            try:
                with open(policy_file, 'r') as f:
                    content = f.read()
                
                # Extract input field patterns
                input_fields = re.findall(r'input\.([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)', content)
                
                for field in input_fields:
                    if field not in field_usage:
                        field_usage[field] = set()
                    field_usage[field].add(str(policy_file))
            
            except Exception:
                continue
        
        # Check for inconsistent field naming
        inconsistencies = []
        field_groups = {}
        
        for field in field_usage:
            base_field = field.split('.')[0]
            if base_field not in field_groups:
                field_groups[base_field] = []
            field_groups[base_field].append(field)
        
        # Look for similar fields that might be inconsistent
        for base_field, fields in field_groups.items():
            if len(fields) > 5:  # Many variations of the same base field
                similar_fields = [f for f in fields if 'config' in f or 'setting' in f or 'enable' in f]
                if len(similar_fields) > 2:
                    inconsistencies.append(f"Potentially inconsistent field naming for {base_field}: {similar_fields[:3]}")
        
        if inconsistencies:
            self.accuracy_issues.extend(inconsistencies)
        
        return len(inconsistencies) == 0
    
    def check_cis_benchmark_alignment(self) -> bool:
        """Check alignment with CIS benchmark numbering and structure"""
        alignment_issues = []
        cis_files = list((self.policies_dir / "cis").rglob("*.rego")) if (self.policies_dir / "cis").exists() else []
        
        for policy_file in cis_files:
            try:
                with open(policy_file, 'r') as f:
                    content = f.read()
                
                # Check for CIS benchmark reference patterns
                cis_patterns = [
                    r'CIS\s+(\d+\.[\d\.]+)',  # CIS 1.1.1 format
                    r'Benchmark\s+(\d+\.[\d\.]+)',
                    r'Control\s+(\d+\.[\d\.]+)'
                ]
                
                found_references = []
                for pattern in cis_patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    found_references.extend(matches)
                
                # Check if references are properly formatted
                for ref in found_references:
                    if not re.match(r'\d+\.\d+(\.\d+)*', ref):
                        alignment_issues.append(f"{policy_file}: Malformed CIS reference '{ref}'")
                
                # Check for missing CIS references in CIS policies
                if 'cis' in str(policy_file).lower() and not found_references:
                    # Only flag if the file contains actual policy rules
                    if re.search(r'^\w+\s*{', content, re.MULTILINE):
                        alignment_issues.append(f"{policy_file}: CIS policy missing benchmark references")
            
            except Exception as e:
                alignment_issues.append(f"Error checking CIS alignment in {policy_file}: {e}")
        
        if alignment_issues:
            self.accuracy_issues.extend(alignment_issues)
            return False
        return True
    
    def check_nist_framework_alignment(self) -> bool:
        """Check alignment with NIST framework structure and identifiers"""
        alignment_issues = []
        nist_files = list((self.policies_dir / "nist").rglob("*.rego")) if (self.policies_dir / "nist").exists() else []
        
        for policy_file in nist_files:
            try:
                with open(policy_file, 'r') as f:
                    content = f.read()
                
                # Check for NIST identifier patterns
                nist_patterns = [
                    r'(AC-\d+)',  # Access Control
                    r'(AU-\d+)',  # Audit
                    r'(CA-\d+)',  # Assessment
                    r'(CM-\d+)',  # Configuration Management
                    r'(PR\.[A-Z]+-\d+)',  # CSF Protect function
                    r'(ID\.[A-Z]+-\d+)',  # CSF Identify function
                    r'(GV\.[A-Z]+-\d+)',  # CSF Govern function
                ]
                
                found_identifiers = []
                for pattern in nist_patterns:
                    matches = re.findall(pattern, content)
                    found_identifiers.extend(matches)
                
                # Check if identifiers are properly formatted
                for identifier in found_identifiers:
                    if 'sp_800_53' in str(policy_file) and not re.match(r'[A-Z]+-\d+', identifier):
                        alignment_issues.append(f"{policy_file}: Malformed SP 800-53 identifier '{identifier}'")
                    elif 'cybersecurity_framework' in str(policy_file) and not re.match(r'[A-Z]+\.[A-Z]+-\d+', identifier):
                        alignment_issues.append(f"{policy_file}: Malformed CSF identifier '{identifier}'")
                
                # Check for missing NIST identifiers in NIST policies
                if 'nist' in str(policy_file).lower() and not found_identifiers:
                    if re.search(r'^\w+\s*{', content, re.MULTILINE):
                        alignment_issues.append(f"{policy_file}: NIST policy missing framework identifiers")
            
            except Exception as e:
                alignment_issues.append(f"Error checking NIST alignment in {policy_file}: {e}")
        
        if alignment_issues:
            self.accuracy_issues.extend(alignment_issues)
            return False
        return True
    
    def generate_accuracy_report(self) -> Dict[str, Any]:
        """Generate comprehensive accuracy report"""
        checks = [
            ("CIS Control Coverage", self.check_cis_control_coverage),
            ("NIST Function Coverage", self.check_nist_function_coverage),
            ("Security Threshold Compliance", self.check_security_threshold_compliance),
            ("Policy Logic Consistency", self.check_policy_logic_consistency),
            ("Input Field Consistency", self.check_input_field_consistency),
            ("CIS Benchmark Alignment", self.check_cis_benchmark_alignment),
            ("NIST Framework Alignment", self.check_nist_framework_alignment)
        ]
        
        results = {}
        overall_accuracy = True
        
        for check_name, check_func in checks:
            try:
                result = check_func()
                results[check_name] = {
                    "passed": result,
                    "issues": [issue for issue in self.accuracy_issues if check_name.lower().replace(' ', '_') in issue.lower()]
                }
                overall_accuracy = overall_accuracy and result
            except Exception as e:
                results[check_name] = {
                    "passed": False,
                    "issues": [f"Check failed with error: {e}"]
                }
                overall_accuracy = False
        
        return {
            "overall_accuracy": overall_accuracy,
            "total_issues": len(self.accuracy_issues),
            "check_results": results,
            "all_issues": self.accuracy_issues,
            "summary": {
                "checks_passed": sum(1 for r in results.values() if r["passed"]),
                "total_checks": len(results),
                "accuracy_score": sum(1 for r in results.values() if r["passed"]) / len(results) * 100
            }
        }

def main():
    parser = argparse.ArgumentParser(description="Check OPA policy accuracy against CIS/NIST standards")
    parser.add_argument("--repo-root", default=".", help="Repository root directory")
    parser.add_argument("--output", help="Output file for accuracy report (JSON)")
    parser.add_argument("--config", help="Configuration file for custom frameworks and controls")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--check", choices=["cis", "nist", "thresholds", "logic", "custom"], help="Run specific check only")
    parser.add_argument("--discover", action="store_true", help="Discover and report policy structure")
    parser.add_argument("--generate-config", help="Generate sample configuration file")
    
    args = parser.parse_args()
    
    if args.generate_config:
        checker = PolicyAccuracyChecker(args.repo_root)
        sample_config = checker._get_default_config()
        with open(args.generate_config, 'w') as f:
            json.dump(sample_config, f, indent=2)
        print(f"📄 Sample configuration generated: {args.generate_config}")
        return 0
    
    checker = PolicyAccuracyChecker(args.repo_root, args.config)
    
    if args.discover:
        structure = checker.discover_policy_structure()
        print(json.dumps(structure, indent=2))
        return 0
    
    print("🎯 Starting policy accuracy check...")
    
    if args.check:
        if args.check == "cis":
            result = checker.check_cis_control_coverage()
        elif args.check == "nist":
            result = checker.check_nist_function_coverage()
        elif args.check == "thresholds":
            result = checker.check_security_threshold_compliance()
        elif args.check == "logic":
            result = checker.check_policy_logic_consistency()
        
        report = {"single_check": args.check, "passed": result, "issues": checker.accuracy_issues}
    else:
        report = checker.generate_accuracy_report()
    
    # Save report if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"📄 Accuracy report saved to {args.output}")
    
    # Print summary
    if not args.check:
        print("\n" + "="*60)
        print("🎯 ACCURACY CHECK SUMMARY")
        print("="*60)
        print(f"Overall Accuracy: {'✅ PASS' if report['overall_accuracy'] else '❌ FAIL'}")
        print(f"Accuracy Score: {report['summary']['accuracy_score']:.1f}%")
        print(f"Checks Passed: {report['summary']['checks_passed']}/{report['summary']['total_checks']}")
        print(f"Total Issues: {report['total_issues']}")
        
        if args.verbose and report['all_issues']:
            print("\n🚨 ACCURACY ISSUES:")
            for issue in report['all_issues'][:10]:  # Show first 10
                print(f"  • {issue}")
            if len(report['all_issues']) > 10:
                print(f"  ... and {len(report['all_issues']) - 10} more issues")
    else:
        print(f"Check '{args.check}': {'✅ PASS' if report['passed'] else '❌ FAIL'}")
        if args.verbose and report['issues']:
            for issue in report['issues']:
                print(f"  • {issue}")
    
    return 0 if (report.get('overall_accuracy', report.get('passed', False))) else 1

if __name__ == "__main__":
    sys.exit(main())