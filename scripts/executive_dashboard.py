#!/usr/bin/env python3
"""
Enterprise Compliance Executive Dashboard
Real-time compliance monitoring and executive reporting system
"""

import json
import os
import subprocess
import datetime
import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import argparse

class ComplianceStatus(Enum):
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"

class RiskLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

@dataclass
class FrameworkMetrics:
    framework: str
    compliance_score: float
    status: ComplianceStatus
    last_assessment: str
    next_assessment: str
    total_controls: int
    compliant_controls: int
    failed_controls: int
    risk_level: RiskLevel
    trending: str  # "improving", "stable", "declining"

@dataclass
class ExecutiveSummary:
    overall_compliance_score: float
    total_frameworks: int
    compliant_frameworks: int
    at_risk_frameworks: int
    critical_issues: int
    upcoming_audits: List[Dict[str, Any]]
    cost_optimization_opportunities: List[str]
    recommendation_priority: List[str]

class ComplianceDashboard:
    def __init__(self, config_file: str = "config/dashboard.json"):
        self.config = self._load_config(config_file)
        self.logger = self._setup_logging()
        self.db_path = self.config.get("database", {}).get("path", "compliance_metrics.db")
        self._init_database()
        
    def _load_config(self, config_file: str) -> Dict[str, Any]:
        """Load dashboard configuration"""
        default_config = {
            "frameworks": {
                "pci_dss": {
                    "enabled": True,
                    "weight": 0.25,
                    "assessment_frequency": "quarterly",
                    "criticality": "high"
                },
                "soc2": {
                    "enabled": True,
                    "weight": 0.25,
                    "assessment_frequency": "monthly",
                    "criticality": "high"
                },
                "iso27001": {
                    "enabled": True,
                    "weight": 0.20,
                    "assessment_frequency": "quarterly",
                    "criticality": "medium"
                },
                "nist_csf": {
                    "enabled": True,
                    "weight": 0.15,
                    "assessment_frequency": "bi-annual",
                    "criticality": "medium"
                },
                "cis": {
                    "enabled": True,
                    "weight": 0.15,
                    "assessment_frequency": "monthly",
                    "criticality": "low"
                }
            },
            "thresholds": {
                "compliant_score": 90.0,
                "partial_score": 70.0,
                "critical_issue_score": 50.0
            },
            "reporting": {
                "executive_frequency": "weekly",
                "operational_frequency": "daily",
                "formats": ["json", "html", "pdf"]
            },
            "database": {
                "path": "compliance_metrics.db",
                "retention_days": 365
            }
        }
        
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    user_config = json.load(f)
                return {**default_config, **user_config}
            return default_config
        except Exception as e:
            print(f"Error loading config: {e}, using defaults")
            return default_config
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        logger = logging.getLogger('compliance_dashboard')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def _init_database(self):
        """Initialize SQLite database for metrics storage"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create tables
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS framework_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    framework TEXT NOT NULL,
                    compliance_score REAL NOT NULL,
                    status TEXT NOT NULL,
                    assessment_date TEXT NOT NULL,
                    total_controls INTEGER NOT NULL,
                    compliant_controls INTEGER NOT NULL,
                    failed_controls INTEGER NOT NULL,
                    risk_level TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS executive_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    overall_score REAL NOT NULL,
                    total_frameworks INTEGER NOT NULL,
                    compliant_frameworks INTEGER NOT NULL,
                    at_risk_frameworks INTEGER NOT NULL,
                    critical_issues INTEGER NOT NULL,
                    summary_data TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS audit_schedule (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    framework TEXT NOT NULL,
                    audit_type TEXT NOT NULL,
                    scheduled_date TEXT NOT NULL,
                    auditor TEXT,
                    status TEXT DEFAULT 'scheduled',
                    created_at TEXT NOT NULL
                )
            ''')
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Database initialization error: {e}")
    
    def collect_framework_metrics(self) -> List[FrameworkMetrics]:
        """Collect current metrics for all enabled frameworks"""
        metrics = []
        
        for framework, config in self.config["frameworks"].items():
            if not config.get("enabled", False):
                continue
                
            try:
                self.logger.info(f"Collecting metrics for {framework}")
                
                # Run OPA evaluation for framework
                framework_metrics = self._evaluate_framework(framework)
                if framework_metrics:
                    metrics.append(framework_metrics)
                    
            except Exception as e:
                self.logger.error(f"Error collecting metrics for {framework}: {e}")
                # Create placeholder metrics for failed collection
                metrics.append(FrameworkMetrics(
                    framework=framework,
                    compliance_score=0.0,
                    status=ComplianceStatus.UNKNOWN,
                    last_assessment=datetime.datetime.now().isoformat(),
                    next_assessment=self._calculate_next_assessment(framework),
                    total_controls=0,
                    compliant_controls=0,
                    failed_controls=0,
                    risk_level=RiskLevel.HIGH,
                    trending="unknown"
                ))
        
        return metrics
    
    def _evaluate_framework(self, framework: str) -> Optional[FrameworkMetrics]:
        """Evaluate compliance for a specific framework using OPA"""
        try:
            # Check if framework policies exist
            policy_dir = f"policies/{framework}"
            if not os.path.exists(policy_dir):
                self.logger.warning(f"Policy directory not found: {policy_dir}")
                return None
            
            # Run OPA evaluation
            cmd = [
                "opa", "eval",
                "-d", policy_dir,
                "-f", "json",
                f"data.{framework}"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                self.logger.error(f"OPA evaluation failed for {framework}: {result.stderr}")
                return None
            
            evaluation_data = json.loads(result.stdout)
            
            # Extract compliance metrics
            compliance_score = self._extract_compliance_score(evaluation_data, framework)
            status = self._determine_status(compliance_score)
            risk_level = self._calculate_risk_level(compliance_score, framework)
            
            # Get historical data for trending
            trending = self._calculate_trending(framework, compliance_score)
            
            # Calculate control counts (simplified)
            total_controls = self._count_total_controls(framework)
            compliant_controls = int((compliance_score / 100) * total_controls)
            failed_controls = total_controls - compliant_controls
            
            return FrameworkMetrics(
                framework=framework,
                compliance_score=compliance_score,
                status=status,
                last_assessment=datetime.datetime.now().isoformat(),
                next_assessment=self._calculate_next_assessment(framework),
                total_controls=total_controls,
                compliant_controls=compliant_controls,
                failed_controls=failed_controls,
                risk_level=risk_level,
                trending=trending
            )
            
        except Exception as e:
            self.logger.error(f"Error evaluating framework {framework}: {e}")
            return None
    
    def _extract_compliance_score(self, evaluation_data: Dict, framework: str) -> float:
        """Extract compliance score from OPA evaluation data"""
        try:
            # Try to find compliance score in various locations
            if evaluation_data.get("result"):
                result = evaluation_data["result"]
                
                # Look for main compliance score
                if f"{framework}_compliance_score" in result:
                    return float(result[f"{framework}_compliance_score"]) * 100
                
                # Look for overall compliance indicator
                if "main" in result and "compliance_score" in result["main"]:
                    return float(result["main"]["compliance_score"]) * 100
                
                # Calculate from passed/total checks
                if "main" in result:
                    main_result = result["main"]
                    if "passed_checks" in main_result and "total_checks" in main_result:
                        passed = main_result["passed_checks"]
                        total = main_result["total_checks"]
                        return (passed / total) * 100 if total > 0 else 0.0
            
            # Fallback: assume moderate compliance if no score found
            self.logger.warning(f"Could not extract compliance score for {framework}, using default")
            return 75.0
            
        except Exception as e:
            self.logger.error(f"Error extracting compliance score for {framework}: {e}")
            return 0.0
    
    def _determine_status(self, score: float) -> ComplianceStatus:
        """Determine compliance status based on score"""
        thresholds = self.config["thresholds"]
        
        if score >= thresholds["compliant_score"]:
            return ComplianceStatus.COMPLIANT
        elif score >= thresholds["partial_score"]:
            return ComplianceStatus.PARTIAL
        else:
            return ComplianceStatus.NON_COMPLIANT
    
    def _calculate_risk_level(self, score: float, framework: str) -> RiskLevel:
        """Calculate risk level based on score and framework criticality"""
        framework_config = self.config["frameworks"].get(framework, {})
        criticality = framework_config.get("criticality", "medium")
        thresholds = self.config["thresholds"]
        
        # Base risk on score
        if score >= thresholds["compliant_score"]:
            base_risk = RiskLevel.LOW
        elif score >= thresholds["partial_score"]:
            base_risk = RiskLevel.MEDIUM
        elif score >= thresholds["critical_issue_score"]:
            base_risk = RiskLevel.HIGH
        else:
            base_risk = RiskLevel.CRITICAL
        
        # Adjust based on framework criticality
        if criticality == "high" and base_risk in [RiskLevel.MEDIUM, RiskLevel.HIGH]:
            # Escalate risk for high-criticality frameworks
            risk_levels = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
            current_index = risk_levels.index(base_risk)
            if current_index < len(risk_levels) - 1:
                return risk_levels[current_index + 1]
        
        return base_risk
    
    def _calculate_trending(self, framework: str, current_score: float) -> str:
        """Calculate trending direction based on historical data"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT compliance_score FROM framework_metrics
                WHERE framework = ? 
                ORDER BY created_at DESC 
                LIMIT 3
            ''', (framework,))
            
            historical_scores = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            if len(historical_scores) < 2:
                return "stable"
            
            # Compare current score with recent history
            recent_avg = sum(historical_scores) / len(historical_scores)
            
            if current_score > recent_avg + 5:
                return "improving"
            elif current_score < recent_avg - 5:
                return "declining"
            else:
                return "stable"
                
        except Exception as e:
            self.logger.error(f"Error calculating trending for {framework}: {e}")
            return "unknown"
    
    def _calculate_next_assessment(self, framework: str) -> str:
        """Calculate next assessment date based on frequency"""
        framework_config = self.config["frameworks"].get(framework, {})
        frequency = framework_config.get("assessment_frequency", "quarterly")
        
        next_date = datetime.datetime.now()
        
        if frequency == "monthly":
            next_date = next_date.replace(day=1) + datetime.timedelta(days=32)
            next_date = next_date.replace(day=1)
        elif frequency == "quarterly":
            current_quarter = (next_date.month - 1) // 3
            next_quarter_month = (current_quarter + 1) * 3 + 1
            if next_quarter_month > 12:
                next_date = next_date.replace(year=next_date.year + 1, month=1, day=1)
            else:
                next_date = next_date.replace(month=next_quarter_month, day=1)
        elif frequency == "bi-annual":
            if next_date.month <= 6:
                next_date = next_date.replace(month=7, day=1)
            else:
                next_date = next_date.replace(year=next_date.year + 1, month=1, day=1)
        else:  # annual
            next_date = next_date.replace(year=next_date.year + 1, month=1, day=1)
        
        return next_date.isoformat()
    
    def _count_total_controls(self, framework: str) -> int:
        """Count total controls for framework (simplified estimation)"""
        control_estimates = {
            "pci_dss": 375,
            "soc2": 200,
            "iso27001": 114,
            "nist_csf": 108,
            "cis": 171
        }
        return control_estimates.get(framework, 100)
    
    def generate_executive_summary(self, metrics: List[FrameworkMetrics]) -> ExecutiveSummary:
        """Generate executive summary from framework metrics"""
        if not metrics:
            return ExecutiveSummary(
                overall_compliance_score=0.0,
                total_frameworks=0,
                compliant_frameworks=0,
                at_risk_frameworks=0,
                critical_issues=0,
                upcoming_audits=[],
                cost_optimization_opportunities=[],
                recommendation_priority=[]
            )
        
        # Calculate weighted overall score
        total_weight = 0
        weighted_score = 0
        compliant_count = 0
        at_risk_count = 0
        critical_issues = 0
        
        for metric in metrics:
            framework_config = self.config["frameworks"].get(metric.framework, {})
            weight = framework_config.get("weight", 0.2)
            
            total_weight += weight
            weighted_score += metric.compliance_score * weight
            
            if metric.status == ComplianceStatus.COMPLIANT:
                compliant_count += 1
            elif metric.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                at_risk_count += 1
            
            if metric.risk_level == RiskLevel.CRITICAL:
                critical_issues += 1
        
        overall_score = weighted_score / total_weight if total_weight > 0 else 0
        
        # Generate upcoming audits
        upcoming_audits = self._get_upcoming_audits(metrics)
        
        # Generate cost optimization opportunities
        cost_opportunities = self._identify_cost_optimizations(metrics)
        
        # Generate priority recommendations
        recommendations = self._generate_priority_recommendations(metrics)
        
        return ExecutiveSummary(
            overall_compliance_score=overall_score,
            total_frameworks=len(metrics),
            compliant_frameworks=compliant_count,
            at_risk_frameworks=at_risk_count,
            critical_issues=critical_issues,
            upcoming_audits=upcoming_audits,
            cost_optimization_opportunities=cost_opportunities,
            recommendation_priority=recommendations
        )
    
    def _get_upcoming_audits(self, metrics: List[FrameworkMetrics]) -> List[Dict[str, Any]]:
        """Get upcoming audit schedule"""
        upcoming = []
        
        for metric in metrics:
            # Calculate days until next assessment
            next_date = datetime.datetime.fromisoformat(metric.next_assessment.replace('Z', '+00:00').replace('+00:00', ''))
            days_until = (next_date - datetime.datetime.now()).days
            
            if days_until <= 90:  # Next 90 days
                upcoming.append({
                    "framework": metric.framework,
                    "type": "compliance_assessment",
                    "scheduled_date": metric.next_assessment,
                    "days_until": days_until,
                    "readiness_score": metric.compliance_score,
                    "risk_level": metric.risk_level.value
                })
        
        return sorted(upcoming, key=lambda x: x["days_until"])
    
    def _identify_cost_optimizations(self, metrics: List[FrameworkMetrics]) -> List[str]:
        """Identify cost optimization opportunities"""
        opportunities = []
        
        # Look for frameworks with overlapping controls
        high_scoring_frameworks = [m for m in metrics if m.compliance_score >= 90]
        
        if len(high_scoring_frameworks) >= 2:
            opportunities.append("Leverage shared controls across high-performing frameworks")
        
        # Look for frameworks with declining trends
        declining_frameworks = [m for m in metrics if m.trending == "declining"]
        if declining_frameworks:
            opportunities.append("Focus investment on declining frameworks to prevent audit failures")
        
        # Look for over-investment opportunities
        excellent_frameworks = [m for m in metrics if m.compliance_score >= 95]
        if excellent_frameworks:
            opportunities.append("Consider reducing frequency of assessments for excellent-performing frameworks")
        
        return opportunities
    
    def _generate_priority_recommendations(self, metrics: List[FrameworkMetrics]) -> List[str]:
        """Generate priority recommendations for executive action"""
        recommendations = []
        
        # Critical issues first
        critical_frameworks = [m for m in metrics if m.risk_level == RiskLevel.CRITICAL]
        for framework in critical_frameworks:
            recommendations.append(f"CRITICAL: Immediate remediation required for {framework.framework}")
        
        # High-risk frameworks
        high_risk_frameworks = [m for m in metrics if m.risk_level == RiskLevel.HIGH]
        for framework in high_risk_frameworks:
            recommendations.append(f"HIGH: Priority attention needed for {framework.framework}")
        
        # Trending issues
        declining_frameworks = [m for m in metrics if m.trending == "declining"]
        for framework in declining_frameworks:
            recommendations.append(f"TREND: Monitor declining performance in {framework.framework}")
        
        # Upcoming audits with low readiness
        low_readiness = [m for m in metrics if m.compliance_score < 80]
        for framework in low_readiness:
            recommendations.append(f"AUDIT PREP: Improve readiness for {framework.framework}")
        
        return recommendations[:10]  # Limit to top 10 recommendations
    
    def store_metrics(self, metrics: List[FrameworkMetrics], summary: ExecutiveSummary):
        """Store metrics and summary in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Store framework metrics
            for metric in metrics:
                cursor.execute('''
                    INSERT INTO framework_metrics 
                    (framework, compliance_score, status, assessment_date, 
                     total_controls, compliant_controls, failed_controls, 
                     risk_level, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    metric.framework,
                    metric.compliance_score,
                    metric.status.value,
                    metric.last_assessment,
                    metric.total_controls,
                    metric.compliant_controls,
                    metric.failed_controls,
                    metric.risk_level.value,
                    datetime.datetime.now().isoformat()
                ))
            
            # Store executive summary
            cursor.execute('''
                INSERT INTO executive_summaries
                (overall_score, total_frameworks, compliant_frameworks,
                 at_risk_frameworks, critical_issues, summary_data, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                summary.overall_compliance_score,
                summary.total_frameworks,
                summary.compliant_frameworks,
                summary.at_risk_frameworks,
                summary.critical_issues,
                json.dumps(asdict(summary)),
                datetime.datetime.now().isoformat()
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error storing metrics: {e}")
    
    def generate_dashboard_report(self, output_format: str = "json") -> str:
        """Generate comprehensive dashboard report"""
        # Collect current metrics
        metrics = self.collect_framework_metrics()
        
        # Generate executive summary
        summary = self.generate_executive_summary(metrics)
        
        # Store in database
        self.store_metrics(metrics, summary)
        
        # Generate report
        report = {
            "report_metadata": {
                "generated_at": datetime.datetime.now().isoformat(),
                "report_type": "executive_dashboard",
                "version": "1.0"
            },
            "executive_summary": asdict(summary),
            "framework_metrics": [asdict(metric) for metric in metrics],
            "risk_analysis": self._generate_risk_analysis(metrics),
            "trend_analysis": self._generate_trend_analysis(metrics),
            "action_items": self._generate_action_items(metrics, summary)
        }
        
        # Save report
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if output_format == "json":
            output_file = f"reports/executive_dashboard_{timestamp}.json"
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2, default=str)
        elif output_format == "html":
            output_file = f"reports/executive_dashboard_{timestamp}.html"
            html_content = self._generate_html_report(report)
            with open(output_file, 'w') as f:
                f.write(html_content)
        
        return output_file
    
    def _generate_risk_analysis(self, metrics: List[FrameworkMetrics]) -> Dict[str, Any]:
        """Generate risk analysis section"""
        risk_distribution = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
        business_impact = []
        
        for metric in metrics:
            risk_distribution[metric.risk_level.value] += 1
            
            if metric.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                framework_config = self.config["frameworks"].get(metric.framework, {})
                criticality = framework_config.get("criticality", "medium")
                
                business_impact.append({
                    "framework": metric.framework,
                    "risk_level": metric.risk_level.value,
                    "compliance_score": metric.compliance_score,
                    "business_criticality": criticality,
                    "potential_impact": self._assess_business_impact(metric.framework, metric.risk_level)
                })
        
        return {
            "risk_distribution": risk_distribution,
            "high_risk_frameworks": len([m for m in metrics if m.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]]),
            "business_impact_analysis": business_impact,
            "overall_risk_score": self._calculate_overall_risk_score(metrics)
        }
    
    def _generate_trend_analysis(self, metrics: List[FrameworkMetrics]) -> Dict[str, Any]:
        """Generate trend analysis section"""
        trending_summary = {"improving": 0, "stable": 0, "declining": 0, "unknown": 0}
        
        for metric in metrics:
            trending_summary[metric.trending] += 1
        
        return {
            "trending_summary": trending_summary,
            "frameworks_improving": [m.framework for m in metrics if m.trending == "improving"],
            "frameworks_declining": [m.framework for m in metrics if m.trending == "declining"],
            "performance_stability": (trending_summary["stable"] / len(metrics)) * 100 if metrics else 0
        }
    
    def _generate_action_items(self, metrics: List[FrameworkMetrics], summary: ExecutiveSummary) -> List[Dict[str, Any]]:
        """Generate prioritized action items"""
        action_items = []
        
        # Critical actions
        for metric in metrics:
            if metric.risk_level == RiskLevel.CRITICAL:
                action_items.append({
                    "priority": "CRITICAL",
                    "framework": metric.framework,
                    "action": f"Immediate remediation required - {metric.failed_controls} controls failing",
                    "timeline": "7 days",
                    "owner": "Compliance Team Lead"
                })
        
        # High-priority actions
        for metric in metrics:
            if metric.risk_level == RiskLevel.HIGH:
                action_items.append({
                    "priority": "HIGH",
                    "framework": metric.framework,
                    "action": f"Address {metric.failed_controls} failing controls",
                    "timeline": "30 days",
                    "owner": "Framework Owner"
                })
        
        # Upcoming audit preparation
        for audit in summary.upcoming_audits:
            if audit["days_until"] <= 30 and audit["readiness_score"] < 80:
                action_items.append({
                    "priority": "HIGH",
                    "framework": audit["framework"],
                    "action": "Audit preparation - improve readiness score",
                    "timeline": f"{audit['days_until']} days",
                    "owner": "Audit Coordinator"
                })
        
        return action_items
    
    def _assess_business_impact(self, framework: str, risk_level: RiskLevel) -> str:
        """Assess business impact of framework risk"""
        impact_matrix = {
            "pci_dss": {
                RiskLevel.CRITICAL: "Loss of payment processing capabilities, regulatory fines up to $500K",
                RiskLevel.HIGH: "Potential payment processor warnings, customer data breach risk"
            },
            "soc2": {
                RiskLevel.CRITICAL: "Loss of enterprise customers, contract violations",
                RiskLevel.HIGH: "Customer audit failures, competitive disadvantage"
            },
            "iso27001": {
                RiskLevel.CRITICAL: "Certification loss, international market access restrictions",
                RiskLevel.HIGH: "Audit findings, certification at risk"
            }
        }
        
        return impact_matrix.get(framework, {}).get(risk_level, "Business operations may be impacted")
    
    def _calculate_overall_risk_score(self, metrics: List[FrameworkMetrics]) -> float:
        """Calculate overall organizational risk score"""
        if not metrics:
            return 0.0
        
        risk_scores = {
            RiskLevel.LOW: 1,
            RiskLevel.MEDIUM: 3,
            RiskLevel.HIGH: 7,
            RiskLevel.CRITICAL: 10
        }
        
        total_weighted_risk = 0
        total_weight = 0
        
        for metric in metrics:
            framework_config = self.config["frameworks"].get(metric.framework, {})
            weight = framework_config.get("weight", 0.2)
            risk_score = risk_scores[metric.risk_level]
            
            total_weighted_risk += risk_score * weight
            total_weight += weight
        
        return total_weighted_risk / total_weight if total_weight > 0 else 0
    
    def _generate_html_report(self, report: Dict[str, Any]) -> str:
        """Generate HTML version of the dashboard report"""
        # Simplified HTML template
        html_template = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Executive Compliance Dashboard</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: #f0f0f0; padding: 20px; border-radius: 5px; }}
                .metric {{ background-color: #e8f4f8; padding: 15px; margin: 10px 0; border-radius: 5px; }}
                .critical {{ background-color: #ffe6e6; }}
                .high {{ background-color: #fff0e6; }}
                .medium {{ background-color: #fff9e6; }}
                .low {{ background-color: #e6ffe6; }}
                table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Executive Compliance Dashboard</h1>
                <p>Generated: {report['report_metadata']['generated_at']}</p>
                <p>Overall Compliance Score: {report['executive_summary']['overall_compliance_score']:.1f}%</p>
            </div>
            
            <h2>Framework Status</h2>
            <table>
                <tr>
                    <th>Framework</th>
                    <th>Score</th>
                    <th>Status</th>
                    <th>Risk Level</th>
                    <th>Trend</th>
                </tr>
        """
        
        # Add framework rows
        for metric in report['framework_metrics']:
            risk_level_str = str(metric['risk_level']).split('.')[-1].lower()
            status_str = str(metric['status']).split('.')[-1]
            html_template += f"""
                <tr class="{risk_level_str}">
                    <td>{metric['framework']}</td>
                    <td>{metric['compliance_score']:.1f}%</td>
                    <td>{status_str}</td>
                    <td>{risk_level_str.upper()}</td>
                    <td>{metric['trending']}</td>
                </tr>
            """
        
        html_template += """
            </table>
            
            <h2>Priority Actions</h2>
            <ul>
        """
        
        # Add action items
        for action in report.get('action_items', []):
            html_template += f"""
                <li class="{action['priority'].lower()}">
                    <strong>{action['priority']}</strong>: {action['action']} 
                    (Timeline: {action['timeline']}, Owner: {action['owner']})
                </li>
            """
        
        html_template += """
            </ul>
        </body>
        </html>
        """
        
        return html_template

def main():
    parser = argparse.ArgumentParser(description="Enterprise Compliance Executive Dashboard")
    parser.add_argument("--config", default="config/dashboard.json",
                       help="Dashboard configuration file")
    parser.add_argument("--format", choices=["json", "html"], default="json",
                       help="Output format")
    parser.add_argument("--output-dir", default="reports",
                       help="Output directory for reports")
    
    args = parser.parse_args()
    
    # Ensure output directory exists
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Initialize dashboard
    dashboard = ComplianceDashboard(args.config)
    
    # Generate report
    output_file = dashboard.generate_dashboard_report(args.format)
    
    print(f"Executive dashboard report generated: {output_file}")

if __name__ == "__main__":
    main()