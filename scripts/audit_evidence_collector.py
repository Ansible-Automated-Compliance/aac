#!/usr/bin/env python3
"""
Enterprise Audit Evidence Collection System
Automated evidence collection and validation for compliance frameworks
"""

import json
try:
    import yaml
except ImportError:
    print("PyYAML not available, using JSON for configuration")
    yaml = None
import os
import subprocess
import datetime
import hashlib
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

class EvidenceType(Enum):
    TECHNICAL = "technical"
    PROCESS = "process"
    OUTCOME = "outcome"

class ValidationStatus(Enum):
    VALID = "valid"
    INVALID = "invalid"
    PENDING = "pending"
    ERROR = "error"

@dataclass
class EvidenceItem:
    id: str
    type: EvidenceType
    framework: str
    requirement: str
    source: str
    content: Any
    checksum: str
    timestamp: str
    validation_status: ValidationStatus
    retention_period: int
    metadata: Dict[str, Any]

class EvidenceCollector:
    def __init__(self, config_path: str = "config/evidence_collection.yaml"):
        self.config = self._load_config(config_path)
        self.logger = self._setup_logging()
        self.evidence_store = []
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load evidence collection configuration"""
        default_config = {
            "frameworks": {
                "pci_dss": {
                    "evidence_retention_years": 3,
                    "collection_frequency": "quarterly",
                    "validation_required": True
                },
                "soc2": {
                    "evidence_retention_years": 2,
                    "collection_frequency": "monthly",
                    "validation_required": True
                },
                "iso27001": {
                    "evidence_retention_years": 3,
                    "collection_frequency": "quarterly",
                    "validation_required": True
                },
                "nist_csf": {
                    "evidence_retention_years": 5,
                    "collection_frequency": "bi-annual",
                    "validation_required": False
                },
                "cis": {
                    "evidence_retention_years": 1,
                    "collection_frequency": "monthly",
                    "validation_required": False
                }
            },
            "storage": {
                "base_path": "/audit-evidence",
                "encryption": True,
                "compression": True,
                "backup_enabled": True
            },
            "validation": {
                "checksum_algorithm": "sha256",
                "digital_signatures": True,
                "timestamp_authority": True
            }
        }
        
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    if yaml is not None:
                        user_config = yaml.safe_load(f)
                    else:
                        # Fallback to JSON if YAML not available
                        user_config = json.load(f)
                # Merge with defaults
                return {**default_config, **user_config}
            return default_config
        except Exception as e:
            print(f"Error loading config: {e}, using defaults")
            return default_config
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        logger = logging.getLogger('evidence_collector')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def collect_technical_evidence(self, framework: str) -> List[EvidenceItem]:
        """Collect technical evidence for specified framework"""
        evidence_items = []
        
        # OPA Policy Evaluation
        opa_evidence = self._collect_opa_evidence(framework)
        evidence_items.extend(opa_evidence)
        
        # Kubernetes/OpenShift Configuration
        k8s_evidence = self._collect_k8s_evidence(framework)
        evidence_items.extend(k8s_evidence)
        
        # System Configuration via Ansible
        ansible_evidence = self._collect_ansible_evidence(framework)
        evidence_items.extend(ansible_evidence)
        
        # Network Configuration
        network_evidence = self._collect_network_evidence(framework)
        evidence_items.extend(network_evidence)
        
        return evidence_items
    
    def _collect_opa_evidence(self, framework: str) -> List[EvidenceItem]:
        """Collect OPA policy evaluation evidence"""
        evidence_items = []
        
        try:
            # Get all policy files for framework
            policy_dir = f"policies/{framework}"
            if not os.path.exists(policy_dir):
                self.logger.warning(f"Policy directory not found: {policy_dir}")
                return evidence_items
            
            # Run OPA evaluation
            cmd = [
                "opa", "eval", 
                "-d", policy_dir,
                "-f", "json",
                "data"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                evaluation_data = json.loads(result.stdout)
                
                evidence_item = EvidenceItem(
                    id=f"opa_eval_{framework}_{self._generate_timestamp()}",
                    type=EvidenceType.TECHNICAL,
                    framework=framework,
                    requirement="all",
                    source="opa_evaluation",
                    content=evaluation_data,
                    checksum=self._calculate_checksum(result.stdout),
                    timestamp=self._generate_timestamp(),
                    validation_status=ValidationStatus.VALID,
                    retention_period=self.config["frameworks"][framework]["evidence_retention_years"],
                    metadata={
                        "command": " ".join(cmd),
                        "policy_directory": policy_dir,
                        "evaluation_size": len(result.stdout)
                    }
                )
                evidence_items.append(evidence_item)
            else:
                self.logger.error(f"OPA evaluation failed: {result.stderr}")
                
        except Exception as e:
            self.logger.error(f"Error collecting OPA evidence: {e}")
        
        return evidence_items
    
    def _collect_k8s_evidence(self, framework: str) -> List[EvidenceItem]:
        """Collect Kubernetes/OpenShift configuration evidence"""
        evidence_items = []
        
        k8s_resources = [
            ("pods", "kubectl get pods -o yaml"),
            ("services", "kubectl get services -o yaml"),
            ("networkpolicies", "kubectl get networkpolicies -o yaml"),
            ("secrets", "kubectl get secrets -o yaml"),
            ("configmaps", "kubectl get configmaps -o yaml"),
            ("rbac", "kubectl get roles,rolebindings,clusterroles,clusterrolebindings -o yaml")
        ]
        
        for resource_type, command in k8s_resources:
            try:
                result = subprocess.run(
                    command.split(), 
                    capture_output=True, 
                    text=True
                )
                
                if result.returncode == 0:
                    evidence_item = EvidenceItem(
                        id=f"k8s_{resource_type}_{framework}_{self._generate_timestamp()}",
                        type=EvidenceType.TECHNICAL,
                        framework=framework,
                        requirement="infrastructure",
                        source=f"kubernetes_{resource_type}",
                        content=result.stdout,
                        checksum=self._calculate_checksum(result.stdout),
                        timestamp=self._generate_timestamp(),
                        validation_status=ValidationStatus.VALID,
                        retention_period=self.config["frameworks"][framework]["evidence_retention_years"],
                        metadata={
                            "resource_type": resource_type,
                            "command": command,
                            "cluster_context": self._get_k8s_context()
                        }
                    )
                    evidence_items.append(evidence_item)
                else:
                    self.logger.warning(f"Failed to collect {resource_type}: {result.stderr}")
                    
            except Exception as e:
                self.logger.error(f"Error collecting {resource_type} evidence: {e}")
        
        return evidence_items
    
    def _collect_ansible_evidence(self, framework: str) -> List[EvidenceItem]:
        """Collect system configuration via Ansible"""
        evidence_items = []
        
        try:
            # Run framework-specific Ansible playbook
            playbook_path = f"ansible/{framework}_evidence_collection.yml"
            
            if os.path.exists(playbook_path):
                cmd = [
                    "ansible-playbook", 
                    playbook_path,
                    "--extra-vars", f"framework={framework}",
                    "-v"
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                evidence_item = EvidenceItem(
                    id=f"ansible_{framework}_{self._generate_timestamp()}",
                    type=EvidenceType.TECHNICAL,
                    framework=framework,
                    requirement="system_configuration",
                    source="ansible_playbook",
                    content={
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "return_code": result.returncode
                    },
                    checksum=self._calculate_checksum(result.stdout + result.stderr),
                    timestamp=self._generate_timestamp(),
                    validation_status=ValidationStatus.VALID if result.returncode == 0 else ValidationStatus.ERROR,
                    retention_period=self.config["frameworks"][framework]["evidence_retention_years"],
                    metadata={
                        "playbook": playbook_path,
                        "command": " ".join(cmd)
                    }
                )
                evidence_items.append(evidence_item)
            else:
                self.logger.warning(f"Ansible playbook not found: {playbook_path}")
                
        except Exception as e:
            self.logger.error(f"Error collecting Ansible evidence: {e}")
        
        return evidence_items
    
    def _collect_network_evidence(self, framework: str) -> List[EvidenceItem]:
        """Collect network configuration and security evidence"""
        evidence_items = []
        
        network_commands = [
            ("firewall_rules", "iptables -L -n -v"),
            ("network_interfaces", "ip addr show"),
            ("routing_table", "ip route show"),
            ("listening_ports", "netstat -tuln"),
            ("network_connections", "ss -tuln")
        ]
        
        for evidence_type, command in network_commands:
            try:
                result = subprocess.run(
                    command.split(), 
                    capture_output=True, 
                    text=True
                )
                
                evidence_item = EvidenceItem(
                    id=f"network_{evidence_type}_{framework}_{self._generate_timestamp()}",
                    type=EvidenceType.TECHNICAL,
                    framework=framework,
                    requirement="network_security",
                    source=f"network_{evidence_type}",
                    content=result.stdout,
                    checksum=self._calculate_checksum(result.stdout),
                    timestamp=self._generate_timestamp(),
                    validation_status=ValidationStatus.VALID if result.returncode == 0 else ValidationStatus.ERROR,
                    retention_period=self.config["frameworks"][framework]["evidence_retention_years"],
                    metadata={
                        "command": command,
                        "return_code": result.returncode
                    }
                )
                evidence_items.append(evidence_item)
                
            except Exception as e:
                self.logger.error(f"Error collecting {evidence_type}: {e}")
        
        return evidence_items
    
    def collect_process_evidence(self, framework: str) -> List[EvidenceItem]:
        """Collect process and procedural evidence"""
        evidence_items = []
        
        # Policy documentation
        policy_evidence = self._collect_policy_evidence(framework)
        evidence_items.extend(policy_evidence)
        
        # Training records
        training_evidence = self._collect_training_evidence(framework)
        evidence_items.extend(training_evidence)
        
        # Incident reports
        incident_evidence = self._collect_incident_evidence(framework)
        evidence_items.extend(incident_evidence)
        
        return evidence_items
    
    def _collect_policy_evidence(self, framework: str) -> List[EvidenceItem]:
        """Collect policy documentation evidence"""
        evidence_items = []
        
        policy_files = [
            f"docs/{framework}_policies.md",
            f"docs/{framework}_procedures.md",
            f"docs/{framework}_standards.md"
        ]
        
        for policy_file in policy_files:
            if os.path.exists(policy_file):
                try:
                    with open(policy_file, 'r') as f:
                        content = f.read()
                    
                    evidence_item = EvidenceItem(
                        id=f"policy_{os.path.basename(policy_file)}_{framework}_{self._generate_timestamp()}",
                        type=EvidenceType.PROCESS,
                        framework=framework,
                        requirement="documentation",
                        source="policy_documentation",
                        content=content,
                        checksum=self._calculate_checksum(content),
                        timestamp=self._generate_timestamp(),
                        validation_status=ValidationStatus.VALID,
                        retention_period=self.config["frameworks"][framework]["evidence_retention_years"],
                        metadata={
                            "file_path": policy_file,
                            "file_size": len(content)
                        }
                    )
                    evidence_items.append(evidence_item)
                    
                except Exception as e:
                    self.logger.error(f"Error reading policy file {policy_file}: {e}")
        
        return evidence_items
    
    def _collect_training_evidence(self, framework: str) -> List[EvidenceItem]:
        """Collect training completion evidence"""
        evidence_items = []
        
        # Mock training data - in production this would connect to LMS
        training_data = {
            "completion_rates": {
                "executive": 100,
                "compliance_team": 100,
                "technical_team": 95,
                "business_users": 88
            },
            "last_updated": self._generate_timestamp(),
            "framework": framework
        }
        
        evidence_item = EvidenceItem(
            id=f"training_{framework}_{self._generate_timestamp()}",
            type=EvidenceType.PROCESS,
            framework=framework,
            requirement="training",
            source="learning_management_system",
            content=training_data,
            checksum=self._calculate_checksum(json.dumps(training_data)),
            timestamp=self._generate_timestamp(),
            validation_status=ValidationStatus.VALID,
            retention_period=self.config["frameworks"][framework]["evidence_retention_years"],
            metadata={
                "source_system": "mock_lms",
                "data_type": "training_completion"
            }
        )
        evidence_items.append(evidence_item)
        
        return evidence_items
    
    def _collect_incident_evidence(self, framework: str) -> List[EvidenceItem]:
        """Collect incident response evidence"""
        evidence_items = []
        
        # Mock incident data - in production this would connect to ITSM
        incident_data = {
            "total_incidents_last_quarter": 2,
            "security_incidents": 0,
            "compliance_incidents": 1,
            "average_resolution_time_hours": 4.5,
            "framework": framework,
            "period": "Q3-2025"
        }
        
        evidence_item = EvidenceItem(
            id=f"incidents_{framework}_{self._generate_timestamp()}",
            type=EvidenceType.OUTCOME,
            framework=framework,
            requirement="incident_management",
            source="incident_management_system",
            content=incident_data,
            checksum=self._calculate_checksum(json.dumps(incident_data)),
            timestamp=self._generate_timestamp(),
            validation_status=ValidationStatus.VALID,
            retention_period=self.config["frameworks"][framework]["evidence_retention_years"],
            metadata={
                "source_system": "mock_itsm",
                "data_type": "incident_metrics"
            }
        )
        evidence_items.append(evidence_item)
        
        return evidence_items
    
    def validate_evidence(self, evidence_item: EvidenceItem) -> ValidationStatus:
        """Validate evidence integrity and completeness"""
        try:
            # Verify checksum
            if isinstance(evidence_item.content, str):
                calculated_checksum = self._calculate_checksum(evidence_item.content)
            else:
                calculated_checksum = self._calculate_checksum(json.dumps(evidence_item.content))
            
            if calculated_checksum != evidence_item.checksum:
                self.logger.error(f"Checksum mismatch for evidence {evidence_item.id}")
                return ValidationStatus.INVALID
            
            # Verify required fields
            required_fields = ['id', 'type', 'framework', 'requirement', 'source', 'content']
            for field in required_fields:
                if not getattr(evidence_item, field):
                    self.logger.error(f"Missing required field {field} for evidence {evidence_item.id}")
                    return ValidationStatus.INVALID
            
            # Framework-specific validation
            if self.config["frameworks"].get(evidence_item.framework, {}).get("validation_required", False):
                framework_valid = self._validate_framework_specific(evidence_item)
                if not framework_valid:
                    return ValidationStatus.INVALID
            
            return ValidationStatus.VALID
            
        except Exception as e:
            self.logger.error(f"Error validating evidence {evidence_item.id}: {e}")
            return ValidationStatus.ERROR
    
    def _validate_framework_specific(self, evidence_item: EvidenceItem) -> bool:
        """Perform framework-specific validation"""
        if evidence_item.framework == "pci_dss":
            return self._validate_pci_evidence(evidence_item)
        elif evidence_item.framework == "soc2":
            return self._validate_soc2_evidence(evidence_item)
        elif evidence_item.framework == "iso27001":
            return self._validate_iso27001_evidence(evidence_item)
        
        return True  # Default to valid for frameworks without specific validation
    
    def _validate_pci_evidence(self, evidence_item: EvidenceItem) -> bool:
        """Validate PCI DSS specific evidence requirements"""
        # Example PCI-specific validation
        if evidence_item.requirement == "network_security":
            if "firewall" not in str(evidence_item.content).lower():
                self.logger.warning(f"PCI network security evidence missing firewall data: {evidence_item.id}")
                return False
        
        return True
    
    def _validate_soc2_evidence(self, evidence_item: EvidenceItem) -> bool:
        """Validate SOC 2 specific evidence requirements"""
        # Example SOC 2 validation
        return True
    
    def _validate_iso27001_evidence(self, evidence_item: EvidenceItem) -> bool:
        """Validate ISO 27001 specific evidence requirements"""
        # Example ISO 27001 validation
        return True
    
    def store_evidence(self, evidence_items: List[EvidenceItem], audit_period: str) -> Dict[str, Any]:
        """Store evidence items with proper organization"""
        storage_results = {
            "stored_count": 0,
            "failed_count": 0,
            "storage_path": "",
            "summary": {}
        }
        
        try:
            # Create storage directory
            base_path = self.config["storage"]["base_path"]
            storage_path = os.path.join(base_path, audit_period)
            os.makedirs(storage_path, exist_ok=True)
            
            # Organize by framework and evidence type
            for evidence_item in evidence_items:
                try:
                    # Validate before storing
                    validation_status = self.validate_evidence(evidence_item)
                    evidence_item.validation_status = validation_status
                    
                    if validation_status == ValidationStatus.VALID:
                        # Create framework directory
                        framework_dir = os.path.join(storage_path, evidence_item.framework)
                        os.makedirs(framework_dir, exist_ok=True)
                        
                        # Create evidence type subdirectory
                        type_dir = os.path.join(framework_dir, evidence_item.type.value)
                        os.makedirs(type_dir, exist_ok=True)
                        
                        # Store evidence
                        evidence_file = os.path.join(type_dir, f"{evidence_item.id}.json")
                        with open(evidence_file, 'w') as f:
                            json.dump(asdict(evidence_item), f, indent=2, default=str)
                        
                        storage_results["stored_count"] += 1
                        
                        # Update summary
                        if evidence_item.framework not in storage_results["summary"]:
                            storage_results["summary"][evidence_item.framework] = {"total": 0, "by_type": {}}
                        
                        storage_results["summary"][evidence_item.framework]["total"] += 1
                        
                        if evidence_item.type.value not in storage_results["summary"][evidence_item.framework]["by_type"]:
                            storage_results["summary"][evidence_item.framework]["by_type"][evidence_item.type.value] = 0
                        
                        storage_results["summary"][evidence_item.framework]["by_type"][evidence_item.type.value] += 1
                        
                    else:
                        storage_results["failed_count"] += 1
                        self.logger.error(f"Failed to store invalid evidence: {evidence_item.id}")
                        
                except Exception as e:
                    storage_results["failed_count"] += 1
                    self.logger.error(f"Error storing evidence {evidence_item.id}: {e}")
            
            storage_results["storage_path"] = storage_path
            
            # Create collection summary
            summary_file = os.path.join(storage_path, "collection_summary.json")
            collection_summary = {
                "audit_period": audit_period,
                "collection_timestamp": self._generate_timestamp(),
                "total_evidence_items": len(evidence_items),
                "storage_results": storage_results,
                "frameworks_collected": list(storage_results["summary"].keys())
            }
            
            with open(summary_file, 'w') as f:
                json.dump(collection_summary, f, indent=2)
            
        except Exception as e:
            self.logger.error(f"Error in evidence storage: {e}")
            storage_results["failed_count"] = len(evidence_items)
        
        return storage_results
    
    def generate_evidence_report(self, audit_period: str, frameworks: List[str]) -> Dict[str, Any]:
        """Generate comprehensive evidence collection report"""
        report = {
            "report_metadata": {
                "audit_period": audit_period,
                "generated_at": self._generate_timestamp(),
                "frameworks": frameworks,
                "generator": "Enterprise Evidence Collector v1.0"
            },
            "collection_summary": {},
            "validation_results": {},
            "compliance_readiness": {},
            "recommendations": []
        }
        
        all_evidence = []
        
        for framework in frameworks:
            self.logger.info(f"Collecting evidence for {framework}")
            
            # Collect all evidence types
            technical_evidence = self.collect_technical_evidence(framework)
            process_evidence = self.collect_process_evidence(framework)
            
            framework_evidence = technical_evidence + process_evidence
            all_evidence.extend(framework_evidence)
            
            # Framework summary
            report["collection_summary"][framework] = {
                "total_items": len(framework_evidence),
                "technical_items": len(technical_evidence),
                "process_items": len(process_evidence),
                "collection_timestamp": self._generate_timestamp()
            }
            
            # Validation summary
            valid_count = sum(1 for item in framework_evidence if item.validation_status == ValidationStatus.VALID)
            report["validation_results"][framework] = {
                "total_items": len(framework_evidence),
                "valid_items": valid_count,
                "validation_rate": (valid_count / len(framework_evidence)) * 100 if framework_evidence else 0
            }
            
            # Compliance readiness assessment
            readiness_score = self._assess_compliance_readiness(framework, framework_evidence)
            report["compliance_readiness"][framework] = readiness_score
        
        # Store all evidence
        storage_results = self.store_evidence(all_evidence, audit_period)
        report["storage_results"] = storage_results
        
        # Generate recommendations
        report["recommendations"] = self._generate_recommendations(report)
        
        return report
    
    def _assess_compliance_readiness(self, framework: str, evidence_items: List[EvidenceItem]) -> Dict[str, Any]:
        """Assess compliance readiness based on evidence quality and coverage"""
        readiness = {
            "overall_score": 0,
            "evidence_coverage": 0,
            "evidence_quality": 0,
            "readiness_level": "NOT_READY",
            "gaps": []
        }
        
        if not evidence_items:
            readiness["gaps"].append("No evidence collected")
            return readiness
        
        # Calculate evidence coverage
        evidence_types = set(item.type for item in evidence_items)
        coverage_score = (len(evidence_types) / 3) * 100  # 3 evidence types total
        readiness["evidence_coverage"] = coverage_score
        
        # Calculate evidence quality
        valid_items = [item for item in evidence_items if item.validation_status == ValidationStatus.VALID]
        quality_score = (len(valid_items) / len(evidence_items)) * 100
        readiness["evidence_quality"] = quality_score
        
        # Calculate overall score
        overall_score = (coverage_score + quality_score) / 2
        readiness["overall_score"] = overall_score
        
        # Determine readiness level
        if overall_score >= 90:
            readiness["readiness_level"] = "AUDIT_READY"
        elif overall_score >= 75:
            readiness["readiness_level"] = "MOSTLY_READY"
        elif overall_score >= 50:
            readiness["readiness_level"] = "PARTIALLY_READY"
        else:
            readiness["readiness_level"] = "NOT_READY"
        
        # Identify gaps
        if EvidenceType.TECHNICAL not in evidence_types:
            readiness["gaps"].append("Missing technical evidence")
        if EvidenceType.PROCESS not in evidence_types:
            readiness["gaps"].append("Missing process evidence")
        if EvidenceType.OUTCOME not in evidence_types:
            readiness["gaps"].append("Missing outcome evidence")
        
        return readiness
    
    def _generate_recommendations(self, report: Dict[str, Any]) -> List[str]:
        """Generate actionable recommendations based on evidence collection results"""
        recommendations = []
        
        # Overall recommendations
        total_frameworks = len(report["collection_summary"])
        ready_frameworks = sum(1 for framework, readiness in report["compliance_readiness"].items() 
                             if readiness["readiness_level"] in ["AUDIT_READY", "MOSTLY_READY"])
        
        if ready_frameworks < total_frameworks:
            recommendations.append(f"Complete evidence collection for {total_frameworks - ready_frameworks} framework(s)")
        
        # Framework-specific recommendations
        for framework, readiness in report["compliance_readiness"].items():
            if readiness["readiness_level"] == "NOT_READY":
                recommendations.append(f"Priority: Address evidence gaps for {framework}")
            elif readiness["evidence_quality"] < 80:
                recommendations.append(f"Improve evidence validation for {framework}")
        
        # Storage recommendations
        if report.get("storage_results", {}).get("failed_count", 0) > 0:
            recommendations.append("Review and resolve evidence storage failures")
        
        return recommendations
    
    def _calculate_checksum(self, content: str) -> str:
        """Calculate SHA-256 checksum of content"""
        algorithm = self.config["validation"]["checksum_algorithm"]
        if algorithm == "sha256":
            return hashlib.sha256(content.encode()).hexdigest()
        elif algorithm == "md5":
            return hashlib.md5(content.encode()).hexdigest()
        else:
            return hashlib.sha256(content.encode()).hexdigest()  # Default to SHA-256
    
    def _generate_timestamp(self) -> str:
        """Generate ISO format timestamp"""
        return datetime.datetime.now().isoformat()
    
    def _get_k8s_context(self) -> str:
        """Get current Kubernetes context"""
        try:
            result = subprocess.run(
                ["kubectl", "config", "current-context"], 
                capture_output=True, 
                text=True
            )
            return result.stdout.strip() if result.returncode == 0 else "unknown"
        except:
            return "unknown"

def main():
    parser = argparse.ArgumentParser(description="Enterprise Audit Evidence Collector")
    parser.add_argument("--frameworks", nargs="+", default=["pci_dss"], 
                       help="Frameworks to collect evidence for")
    parser.add_argument("--audit-period", default=f"Q3-2025", 
                       help="Audit period identifier")
    parser.add_argument("--config", default="config/evidence_collection.yaml",
                       help="Configuration file path")
    parser.add_argument("--output", default="evidence_collection_report.json",
                       help="Output report file")
    
    args = parser.parse_args()
    
    # Initialize collector
    collector = EvidenceCollector(args.config)
    
    # Generate evidence report
    report = collector.generate_evidence_report(args.audit_period, args.frameworks)
    
    # Save report
    with open(args.output, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"Evidence collection completed for {args.frameworks}")
    print(f"Report saved to: {args.output}")
    print(f"Evidence stored in: {report['storage_results']['storage_path']}")
    
    # Print summary
    for framework in args.frameworks:
        readiness = report["compliance_readiness"][framework]
        print(f"{framework}: {readiness['readiness_level']} ({readiness['overall_score']:.1f}%)")

if __name__ == "__main__":
    main()