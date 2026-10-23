#!/usr/bin/env python3
"""
Compliance Reporting Tool for OPA CIS/NIST/ISO 27001/SOC 2 Libraries

This tool generates comprehensive compliance reports across all supported frameworks,
providing executive summaries, detailed findings, and actionable recommendations.
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
import argparse
from datetime import datetime
import tempfile
import csv

class ComplianceReporter:
    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root)
        self.policies_dir = self.repo_root / "policies"
        self.reports_dir = self.repo_root / "reports"
        self.reports_dir.mkdir(exist_ok=True)
        
        # Supported frameworks
        self.frameworks = {
            "cis": {
                "name": "CIS Benchmarks",
                "policies": ["cis"],
                "test_files": ["comprehensive_test_suite.rego"]
            },
            "sox": {
                "name": "Sarbanes-Oxley Act (SOX)",
                "policies": ["sox_clean"],
                "test_files": ["test_sox_input.json"]
            },
            "nist_csf": {
                "name": "NIST Cybersecurity Framework 2.0",
                "policies": ["nist.csf"],
                "test_files": ["comprehensive_test_suite.rego"]
            },
            "nist_sp800_53": {
                "name": "NIST SP 800-53 Rev 5",
                "policies": ["nist.sp800_53"],
                "test_files": ["comprehensive_test_suite.rego"]
            },
            "nist_sp800_171": {
                "name": "NIST SP 800-171 Rev 3",
                "policies": ["nist.sp800_171"],
                "test_files": ["comprehensive_test_suite.rego"]
            },
            "nist_rmf": {
                "name": "NIST Risk Management Framework",
                "policies": ["nist.rmf"],
                "test_files": ["comprehensive_test_suite.rego"]
            },
            "iso27001": {
                "name": "ISO/IEC 27001:2022",
                "policies": ["iso27001"],
                "test_files": ["iso27001_test_suite.rego"]
            },
            "soc2": {
                "name": "SOC 2 Trust Service Criteria",
                "policies": ["soc2"],
                "test_files": ["soc2_test_suite.rego"]
            },
            "pci_dss": {
                "name": "PCI DSS v4.0",
                "policies": ["pci_dss"],
                "test_files": ["pci_dss_test_suite.rego"]
            }
        }
    
    def run_opa_eval(self, policy_query: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Run OPA evaluation with given query and input data"""
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(input_data, f)
                input_file = f.name
            
            cmd = [
                "opa", "eval",
                "-d", str(self.policies_dir),
                "-i", input_file,
                "--format", "json",
                policy_query
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                return json.loads(result.stdout)
            else:
                return {"error": result.stderr, "query": policy_query}
                
        except Exception as e:
            return {"error": str(e), "query": policy_query}
        finally:
            try:
                Path(input_file).unlink()
            except:
                pass
    
    def generate_sample_data(self, framework: str) -> Dict[str, Any]:
        """Generate sample compliant data for testing"""
        if framework == "cis":
            return {
                "os_family": "RedHat",
                "distribution": "CentOS",
                "distribution_version": "9.0",
                "selinux_status": "enforcing",
                "firewall_enabled": True,
                "ssh_port": 22,
                "loaded_modules": ["ext4", "xfs", "btrfs"],
                "mounts": {
                    "/tmp": {
                        "device": "/dev/sda2",
                        "fstype": "ext4",
                        "options": ["rw", "nodev", "nosuid", "noexec"]
                    }
                },
                "net_ipv4_ip_forward": 0,
                "ssh_config": [
                    "Protocol 2",
                    "PermitRootLogin no",
                    "MaxAuthTries 4"
                ]
            }
        elif framework in ["nist_csf", "nist_sp800_53", "nist_sp800_171", "nist_rmf"]:
            return {
                "governance": {
                    "cybersecurity_strategy": {
                        "documented": True,
                        "approved_by_leadership": True,
                        "regularly_reviewed": True
                    }
                },
                "access_control": {
                    "identity_management": {
                        "centralized_system": True,
                        "lifecycle_management": True,
                        "credential_policies": True
                    }
                },
                "ac_controls": {
                    "session_lock": {
                        "inactivity_timeout": 900,
                        "pattern_hiding": True,
                        "authentication_required": True
                    },
                    "logon_attempts": {
                        "lockout_configured": True,
                        "maximum_attempts": 3,
                        "lockout_duration": 15
                    }
                },
                "cui_access": {
                    "user_authorization": {
                        "all_users_authorized": True,
                        "process_authorization": True,
                        "device_authorization": True
                    }
                },
                "system_categorization": {
                    "confidentiality": {"impact_level": "moderate"},
                    "integrity": {"impact_level": "high"},
                    "availability": {"impact_level": "low"},
                    "overall_impact_level": "high"
                }
            }
        elif framework == "iso27001":
            return {
                "access_control": {
                    "policy": {
                        "documented": True,
                        "approved": True,
                        "communicated": True
                    },
                    "access_rules": {
                        "defined": True,
                        "enforced": True
                    }
                },
                "user_management": {
                    "registration": {
                        "formal_process": True,
                        "authorization_required": True,
                        "documented": True
                    },
                    "unauthorized_users": [],
                    "provisioning": {
                        "least_privilege": True,
                        "role_based": True,
                        "approval_required": True,
                        "automated_tools": True
                    }
                },
                "privileged_access": {
                    "allocation_restricted": True,
                    "regular_review": True,
                    "monitoring_enabled": True,
                    "multi_factor_auth": True,
                    "shared_accounts": []
                },
                "authentication": {
                    "password_policy": {
                        "min_length": 12,
                        "complexity_required": True,
                        "expiry_enabled": True,
                        "history_count": 15,
                        "lockout_enabled": True
                    },
                    "mfa": {
                        "enabled": True,
                        "required_for_admin": True,
                        "required_for_remote": True
                    },
                    "secrets": {
                        "encrypted_storage": True,
                        "access_controlled": True,
                        "regular_rotation": True,
                        "secure_transmission": True
                    }
                },
                "cryptography": {
                    "policy": {
                        "documented": True,
                        "approved": True,
                        "communicated": True,
                        "regularly_reviewed": True,
                        "approved_algorithms": ["AES", "RSA", "ECC"],
                        "key_management_addressed": True,
                        "encryption_requirements": True
                    },
                    "algorithms_in_use": ["AES", "RSA", "ECC", "SHA256", "TLS1.3"]
                },
                "operations": {
                    "procedures": {
                        "documented": True,
                        "approved": True,
                        "regularly_updated": True,
                        "accessible_to_users": True,
                        "version_controlled": True
                    }
                },
                "network": {
                    "security_policy": {
                        "documented": True,
                        "implemented": True,
                        "regularly_reviewed": True
                    },
                    "protocols": {
                        "enabled": ["TLS", "SSH", "SFTP", "HTTPS", "IPSec"]
                    }
                },
                "development": {
                    "policy": {
                        "documented": True,
                        "approved": True,
                        "communicated": True,
                        "regularly_updated": True,
                        "practices_covered": ["secure_coding", "code_review", "security_testing"]
                    }
                }
            }
        else:
            return {}
    
    def evaluate_framework_compliance(self, framework: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate compliance for a specific framework"""
        framework_info = self.frameworks.get(framework)
        if not framework_info:
            return {"error": f"Unknown framework: {framework}"}
        
        results = {
            "framework": framework_info["name"],
            "timestamp": datetime.now().isoformat(),
            "overall_compliance": False,
            "detailed_results": {},
            "summary": {},
            "recommendations": []
        }
        
        # Framework-specific queries
        if framework == "cis":
            queries = {
                "overall": "data.cis.allow",
                "filesystem": "data.cis.filesystem",
                "network": "data.cis.network",
                "access_control": "data.cis.access_control"
            }
        elif framework == "nist_csf":
            queries = {
                "overall": "data.nist.csf.govern.organizational_strategy_established",
                "govern": "data.nist.csf.govern",
                "protect": "data.nist.csf.protect"
            }
        elif framework == "nist_sp800_53":
            queries = {
                "overall": "data.nist.sp800_53.access_control.session_lock",
                "access_control": "data.nist.sp800_53.access_control"
            }
        elif framework == "nist_sp800_171":
            queries = {
                "overall": "data.nist.sp800_171.access_control.authorized_access_only",
                "access_control": "data.nist.sp800_171.access_control"
            }
        elif framework == "nist_rmf":
            queries = {
                "overall": "data.nist.rmf.categorize.high_water_mark_properly_applied",
                "categorize": "data.nist.rmf.categorize"
            }
        elif framework == "iso27001":
            queries = {
                "overall": "data.iso27001.allow",
                "access_control": "data.iso27001.access_control.compliant",
                "cryptography": "data.iso27001.cryptography.compliant",
                "operations_security": "data.iso27001.operations_security.compliant",
                "communications_security": "data.iso27001.communications_security.compliant",
                "system_acquisition_maintenance": "data.iso27001.system_acquisition_maintenance.compliant",
                "compliance_report": "data.iso27001.iso27001_compliance_report"
            }
        elif framework == "soc2":
            queries = {
                "overall": "data.soc2.main.overall_soc2_compliant",
                "security": "data.soc2.security.access_controls.overall_security_compliant",
                "availability": "data.soc2.availability.system_availability.overall_availability_compliant", 
                "processing_integrity": "data.soc2.processing_integrity.data_processing.overall_processing_integrity_compliant",
                "confidentiality": "data.soc2.confidentiality.data_confidentiality.overall_confidentiality_compliant",
                "privacy": "data.soc2.privacy.data_privacy.overall_privacy_compliant",
                "infrastructure_network": "data.soc2.infrastructure.network.network_infrastructure.overall_network_infrastructure_compliant",
                "infrastructure_security": "data.soc2.infrastructure.security.security_infrastructure.overall_security_infrastructure_compliant",
                "infrastructure_systems": "data.soc2.infrastructure.systems.systems_infrastructure.overall_systems_infrastructure_compliant",
                "infrastructure_storage": "data.soc2.infrastructure.storage.storage_infrastructure.overall_storage_infrastructure_compliant",
                "infrastructure_apps": "data.soc2.infrastructure.applications_services.applications_services.overall_applications_services_compliant",
                "compliance_score": "data.soc2.main.soc2_compliance_score",
                "detailed_findings": "data.soc2.main.soc2_detailed_findings"
            }
        elif framework == "pci_dss":
            queries = {
                "overall": "data.pci_dss.main.overall_pci_dss_compliant",
                "requirement_1": "data.pci_dss.network_security.requirement_1.pci_requirement_1_compliant",
                "requirement_3": "data.pci_dss.data_protection.requirement_3.pci_requirement_3_compliant",
                "compliance_score": "data.pci_dss.main.pci_dss_compliance_score",
                "detailed_findings": "data.pci_dss.main.pci_dss_detailed_findings",
                "validation_level": "data.pci_dss.main.pci_validation_level"
            }
        elif framework == "sox":
            queries = {
                "overall": "data.sox.main.sox_compliant",
                "section_302": "data.sox.main.section_302_compliant",
                "section_404": "data.sox.main.section_404_compliant",
                "section_409": "data.sox.main.section_409_compliant",
                "compliance_score": "data.sox.main.sox_compliance_score",
                "detailed_findings": "data.sox.main.sox_detailed_findings",
                "compliance_level": "data.sox.main.sox_compliance_level",
                "overall_assessment": "data.sox.main.overall_sox_assessment"
            }
        else:
            queries = {"overall": "data.unknown"}
        
        # Evaluate each query
        for query_name, query in queries.items():
            result = self.run_opa_eval(query, input_data)
            results["detailed_results"][query_name] = result
            
            if query_name == "overall":
                # Determine overall compliance
                if "result" in result and result["result"]:
                    results["overall_compliance"] = bool(result["result"][0].get("expressions", [{}])[0].get("value", False))
        
        # Generate summary and recommendations
        results["summary"] = self._generate_summary(framework, results["detailed_results"])
        results["recommendations"] = self._generate_recommendations(framework, results["detailed_results"])
        
        return results
    
    def _generate_summary(self, framework: str, detailed_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary statistics"""
        total_checks = len(detailed_results)
        passed_checks = 0
        
        for check_name, result in detailed_results.items():
            if "result" in result and result["result"]:
                try:
                    if result["result"][0].get("expressions", [{}])[0].get("value", False):
                        passed_checks += 1
                except (IndexError, KeyError, TypeError):
                    pass
        
        compliance_percentage = (passed_checks / total_checks * 100) if total_checks > 0 else 0
        
        return {
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "failed_checks": total_checks - passed_checks,
            "compliance_percentage": round(compliance_percentage, 1),
            "status": "COMPLIANT" if compliance_percentage >= 80 else "NON_COMPLIANT"
        }
    
    def _generate_recommendations(self, framework: str, detailed_results: Dict[str, Any]) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []
        
        for check_name, result in detailed_results.items():
            if "result" in result and result["result"]:
                try:
                    if not result["result"][0].get("expressions", [{}])[0].get("value", False):
                        if framework == "cis":
                            if check_name == "filesystem":
                                recommendations.append("Configure filesystem security: Enable nodev, nosuid, noexec options on /tmp")
                            elif check_name == "network":
                                recommendations.append("Secure network configuration: Disable IP forwarding and packet redirects")
                            elif check_name == "access_control":
                                recommendations.append("Strengthen access controls: Disable SSH root login and limit authentication attempts")
                        elif framework == "iso27001":
                            if check_name == "access_control":
                                recommendations.append("Implement ISO 27001 A.9: Strengthen access control policies and user management")
                            elif check_name == "cryptography":
                                recommendations.append("Implement ISO 27001 A.10: Deploy cryptographic controls and key management")
                            elif check_name == "operations_security":
                                recommendations.append("Implement ISO 27001 A.12: Enhance operations security and monitoring")
                        elif "nist" in framework:
                            recommendations.append(f"Address NIST {framework.upper()} requirements for {check_name}")
                except (IndexError, KeyError, TypeError):
                    pass
        
        if not recommendations:
            recommendations.append("All checks passed - maintain current security posture")
        
        return recommendations[:5]  # Limit to top 5 recommendations
    
    def generate_comprehensive_report(self, input_data: Optional[Dict[str, Any]] = None, 
                                    frameworks: Optional[List[str]] = None) -> Dict[str, Any]:
        """Generate comprehensive compliance report across all frameworks"""
        if frameworks is None:
            frameworks = list(self.frameworks.keys())
        
        report = {
            "report_metadata": {
                "generated_at": datetime.now().isoformat(),
                "generated_by": "OPA Compliance Reporter",
                "frameworks_evaluated": frameworks,
                "report_version": "1.0"
            },
            "executive_summary": {},
            "framework_results": {},
            "cross_framework_analysis": {},
            "recommendations": []
        }
        
        framework_summaries = []
        all_recommendations = []
        
        for framework in frameworks:
            print(f"📊 Evaluating {self.frameworks[framework]['name']}...")
            
            # Use provided data or generate sample data
            test_data = input_data if input_data else self.generate_sample_data(framework)
            
            # Evaluate framework
            framework_result = self.evaluate_framework_compliance(framework, test_data)
            report["framework_results"][framework] = framework_result
            
            # Collect for executive summary
            if "summary" in framework_result:
                framework_summaries.append({
                    "framework": framework,
                    "name": self.frameworks[framework]["name"],
                    "compliance_percentage": framework_result["summary"].get("compliance_percentage", 0),
                    "status": framework_result["summary"].get("status", "UNKNOWN")
                })
            
            # Collect recommendations
            all_recommendations.extend(framework_result.get("recommendations", []))
        
        # Generate executive summary
        if framework_summaries:
            avg_compliance = sum(f["compliance_percentage"] for f in framework_summaries) / len(framework_summaries)
            compliant_frameworks = [f for f in framework_summaries if f["status"] == "COMPLIANT"]
            
            report["executive_summary"] = {
                "overall_compliance_score": round(avg_compliance, 1),
                "compliant_frameworks": len(compliant_frameworks),
                "total_frameworks": len(framework_summaries),
                "compliance_rate": f"{len(compliant_frameworks)}/{len(framework_summaries)}",
                "overall_status": "COMPLIANT" if len(compliant_frameworks) >= len(framework_summaries) * 0.8 else "NON_COMPLIANT",
                "framework_breakdown": framework_summaries
            }
        
        # Cross-framework analysis
        report["cross_framework_analysis"] = self._analyze_cross_framework_alignment(report["framework_results"])
        
        # Prioritized recommendations
        report["recommendations"] = list(set(all_recommendations))[:10]  # Top 10 unique recommendations
        
        return report
    
    def _analyze_cross_framework_alignment(self, framework_results: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze alignment between different frameworks"""
        analysis = {
            "common_control_areas": [],
            "framework_gaps": [],
            "alignment_score": 0
        }
        
        # Common control areas across frameworks
        common_areas = ["access_control", "cryptography", "network_security", "monitoring"]
        
        for area in common_areas:
            area_compliance = []
            for framework, results in framework_results.items():
                if area in results.get("detailed_results", {}):
                    # Check if this area passed
                    result = results["detailed_results"][area]
                    if "result" in result and result["result"]:
                        try:
                            passed = result["result"][0].get("expressions", [{}])[0].get("value", False)
                            area_compliance.append(passed)
                        except (IndexError, KeyError, TypeError):
                            area_compliance.append(False)
            
            if area_compliance:
                compliance_rate = sum(area_compliance) / len(area_compliance)
                analysis["common_control_areas"].append({
                    "area": area,
                    "compliance_rate": round(compliance_rate * 100, 1),
                    "frameworks_compliant": sum(area_compliance),
                    "total_frameworks": len(area_compliance)
                })
        
        # Calculate overall alignment score
        if analysis["common_control_areas"]:
            alignment_score = sum(area["compliance_rate"] for area in analysis["common_control_areas"]) / len(analysis["common_control_areas"])
            analysis["alignment_score"] = round(alignment_score, 1)
        
        return analysis
    
    def save_report(self, report: Dict[str, Any], format: str = "json", filename: Optional[str] = None) -> str:
        """Save report to file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"compliance_report_{timestamp}"
        
        if format == "json":
            filepath = self.reports_dir / f"{filename}.json"
            with open(filepath, 'w') as f:
                json.dump(report, f, indent=2)
        elif format == "html":
            filepath = self.reports_dir / f"{filename}.html"
            html_content = self._generate_html_report(report)
            with open(filepath, 'w') as f:
                f.write(html_content)
        elif format == "csv":
            filepath = self.reports_dir / f"{filename}.csv"
            self._generate_csv_report(report, filepath)
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        return str(filepath)
    
    def _generate_html_report(self, report: Dict[str, Any]) -> str:
        """Generate HTML compliance report"""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Compliance Report - {report['report_metadata']['generated_at'][:10]}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px; margin-bottom: 30px; }}
        .summary {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .framework {{ margin: 20px 0; padding: 20px; border: 1px solid #ddd; border-radius: 8px; }}
        .compliant {{ color: #28a745; font-weight: bold; }}
        .non-compliant {{ color: #dc3545; font-weight: bold; }}
        .score {{ font-size: 2em; font-weight: bold; text-align: center; }}
        .recommendation {{ background: #fff3cd; padding: 10px; margin: 5px 0; border-left: 4px solid #ffc107; }}
        table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .progress-bar {{ background: #e9ecef; border-radius: 4px; overflow: hidden; height: 20px; }}
        .progress-fill {{ background: #28a745; height: 100%; transition: width 0.3s ease; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🛡️ Compliance Report</h1>
        <p>Generated: {report['report_metadata']['generated_at']}</p>
        <p>Frameworks: {', '.join(report['report_metadata']['frameworks_evaluated'])}</p>
    </div>
        """
        
        # Executive Summary
        if "executive_summary" in report:
            summary = report["executive_summary"]
            html += f"""
    <div class="summary">
        <h2>📊 Executive Summary</h2>
        <div class="score">
            <span class="{'compliant' if summary.get('overall_status') == 'COMPLIANT' else 'non-compliant'}">
                {summary.get('overall_compliance_score', 0)}% Compliant
            </span>
        </div>
        <div class="progress-bar">
            <div class="progress-fill" style="width: {summary.get('overall_compliance_score', 0)}%"></div>
        </div>
        <p><strong>Status:</strong> <span class="{'compliant' if summary.get('overall_status') == 'COMPLIANT' else 'non-compliant'}">{summary.get('overall_status', 'UNKNOWN')}</span></p>
        <p><strong>Frameworks Compliant:</strong> {summary.get('compliance_rate', '0/0')}</p>
    </div>
            """
        
        # Framework Results
        html += "<h2>📋 Framework Details</h2>"
        for framework, results in report.get("framework_results", {}).items():
            framework_name = results.get("framework", framework)
            summary = results.get("summary", {})
            
            html += f"""
    <div class="framework">
        <h3>{framework_name}</h3>
        <p><strong>Compliance:</strong> <span class="{'compliant' if summary.get('status') == 'COMPLIANT' else 'non-compliant'}">{summary.get('compliance_percentage', 0)}%</span></p>
        <p><strong>Checks:</strong> {summary.get('passed_checks', 0)}/{summary.get('total_checks', 0)} passed</p>
        <div class="progress-bar">
            <div class="progress-fill" style="width: {summary.get('compliance_percentage', 0)}%"></div>
        </div>
    </div>
            """
        
        # Recommendations
        if report.get("recommendations"):
            html += "<h2>💡 Recommendations</h2>"
            for i, rec in enumerate(report["recommendations"], 1):
                html += f'<div class="recommendation">{i}. {rec}</div>'
        
        # Cross-framework Analysis
        if "cross_framework_analysis" in report:
            analysis = report["cross_framework_analysis"]
            html += f"""
    <h2>🔗 Cross-Framework Analysis</h2>
    <div class="summary">
        <p><strong>Alignment Score:</strong> {analysis.get('alignment_score', 0)}%</p>
        <table>
            <tr><th>Control Area</th><th>Compliance Rate</th><th>Frameworks</th></tr>
            """
            for area in analysis.get("common_control_areas", []):
                html += f"""
            <tr>
                <td>{area['area'].replace('_', ' ').title()}</td>
                <td>{area['compliance_rate']}%</td>
                <td>{area['frameworks_compliant']}/{area['total_frameworks']}</td>
            </tr>
                """
            html += "</table></div>"
        
        html += """
    <div style="margin-top: 40px; padding: 20px; background: #f8f9fa; border-radius: 8px; text-align: center;">
        <p><em>Generated by OPA Compliance Reporter</em></p>
        <p>For detailed technical findings, refer to the JSON report or run individual framework assessments.</p>
    </div>
</body>
</html>
        """
        
        return html
    
    def _generate_csv_report(self, report: Dict[str, Any], filepath: Path):
        """Generate CSV compliance report"""
        with open(filepath, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Header
            writer.writerow(['Framework', 'Compliance %', 'Status', 'Passed Checks', 'Total Checks', 'Recommendations'])
            
            # Framework results
            for framework, results in report.get("framework_results", {}).items():
                framework_name = results.get("framework", framework)
                summary = results.get("summary", {})
                recommendations = "; ".join(results.get("recommendations", []))
                
                writer.writerow([
                    framework_name,
                    summary.get('compliance_percentage', 0),
                    summary.get('status', 'UNKNOWN'),
                    summary.get('passed_checks', 0),
                    summary.get('total_checks', 0),
                    recommendations
                ])

def main():
    parser = argparse.ArgumentParser(description="Generate compliance reports for OPA policies")
    parser.add_argument("--repo-root", default=".", help="Repository root directory")
    parser.add_argument("--frameworks", nargs="+", 
                       choices=["cis", "nist_csf", "nist_sp800_53", "nist_sp800_171", "nist_rmf", "iso27001", "soc2", "pci_dss", "sox"],
                       help="Frameworks to evaluate")
    parser.add_argument("--input-file", help="JSON file with input data for evaluation")
    parser.add_argument("--output-format", choices=["json", "html", "csv"], default="html",
                       help="Output format for report")
    parser.add_argument("--output-file", help="Output filename (without extension)")
    parser.add_argument("--sample-data", action="store_true", 
                       help="Use sample compliant data for demonstration")
    
    args = parser.parse_args()
    
    reporter = ComplianceReporter(args.repo_root)
    
    # Load input data
    input_data = None
    if args.input_file:
        try:
            with open(args.input_file, 'r') as f:
                input_data = json.load(f)
            print(f"📁 Loaded input data from {args.input_file}")
        except Exception as e:
            print(f"❌ Error loading input file: {e}")
            return 1
    elif not args.sample_data:
        print("⚠️  No input data provided. Use --sample-data for demonstration or --input-file for real data.")
        return 1
    
    # Generate comprehensive report
    print("🔍 Generating compliance report...")
    report = reporter.generate_comprehensive_report(input_data, args.frameworks)
    
    # Save report
    try:
        output_file = reporter.save_report(report, args.output_format, args.output_file)
        print(f"✅ Report saved to: {output_file}")
        
        # Print executive summary
        if "executive_summary" in report:
            summary = report["executive_summary"]
            print(f"\n📊 EXECUTIVE SUMMARY")
            print("=" * 50)
            print(f"Overall Compliance: {summary.get('overall_compliance_score', 0)}%")
            print(f"Status: {summary.get('overall_status', 'UNKNOWN')}")
            print(f"Compliant Frameworks: {summary.get('compliance_rate', '0/0')}")
            
            if args.frameworks or True:  # Show framework breakdown
                print(f"\n📋 Framework Breakdown:")
                for fw in summary.get("framework_breakdown", []):
                    status_icon = "✅" if fw["status"] == "COMPLIANT" else "❌"
                    print(f"  {status_icon} {fw['name']}: {fw['compliance_percentage']}%")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error generating report: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())