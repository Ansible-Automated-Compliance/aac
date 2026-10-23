#!/usr/bin/env python3
"""
Compliance Dashboard and Reporting Framework
Ansible Automation Platform 2.6 + OPA + Database Integration

This script provides comprehensive compliance reporting and dashboard functionality
for the AAP-OPA-Database integration architecture.
"""

import os
import sys
import json
import logging
import argparse
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from jinja2 import Template, Environment, FileSystemLoader
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class ComplianceMetrics:
    """Data class for compliance metrics"""
    total_systems: int
    compliant_systems: int
    non_compliant_systems: int
    compliance_percentage: float
    total_violations: int
    critical_violations: int
    high_violations: int
    medium_violations: int
    low_violations: int

@dataclass
class SystemSummary:
    """Data class for individual system summary"""
    hostname: str
    platform: str
    environment: str
    is_compliant: bool
    compliance_score: float
    total_violations: int
    last_assessed: datetime

class ComplianceDashboard:
    """Main compliance dashboard and reporting class"""
    
    def __init__(self, db_config: Dict[str, Any]):
        """Initialize dashboard with database configuration"""
        self.db_config = db_config
        self.conn = None
        self.template_env = Environment(
            loader=FileSystemLoader('templates') if os.path.exists('templates') else Environment()
        )
        
    def connect_database(self):
        """Establish database connection"""
        try:
            self.conn = psycopg2.connect(**self.db_config)
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
            
    def close_database(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

    def execute_query(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        """Execute SQL query and return results"""
        if not self.conn:
            self.connect_database()
            
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, params or {})
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise

    def get_executive_summary(self) -> Dict[str, ComplianceMetrics]:
        """Generate executive compliance summary by environment"""
        query = """
        SELECT 
            environment,
            total_systems,
            compliant_systems,
            compliance_percentage,
            non_compliant_systems,
            total_violations
        FROM compliance_executive_summary
        ORDER BY environment
        """
        
        results = self.execute_query(query)
        summary = {}
        
        for row in results:
            # Get violation breakdown for this environment
            violation_query = """
            SELECT 
                cv.severity,
                COUNT(*) as count
            FROM compliance_violations cv
            JOIN compliance_assessments ca ON cv.assessment_id = ca.id
            JOIN systems s ON ca.system_id = s.id
            WHERE s.environment = %(env)s 
              AND cv.status IN ('open', 'in_progress')
            GROUP BY cv.severity
            """
            
            violations = self.execute_query(violation_query, {'env': row['environment']})
            violation_counts = {v['severity']: v['count'] for v in violations}
            
            summary[row['environment']] = ComplianceMetrics(
                total_systems=row['total_systems'] or 0,
                compliant_systems=row['compliant_systems'] or 0,
                non_compliant_systems=row['non_compliant_systems'] or 0,
                compliance_percentage=float(row['compliance_percentage'] or 0),
                total_violations=row['total_violations'] or 0,
                critical_violations=violation_counts.get('CRITICAL', 0),
                high_violations=violation_counts.get('HIGH', 0),
                medium_violations=violation_counts.get('MEDIUM', 0),
                low_violations=violation_counts.get('LOW', 0)
            )
            
        return summary

    def get_platform_breakdown(self) -> List[Dict]:
        """Get compliance breakdown by platform"""
        query = """
        SELECT 
            platform,
            policy_name,
            total_systems,
            compliant_count,
            compliance_rate,
            total_violations,
            avg_compliance_score
        FROM platform_compliance_summary
        ORDER BY compliance_rate DESC, platform
        """
        
        return self.execute_query(query)

    def get_critical_violations(self, limit: int = 50) -> List[Dict]:
        """Get critical violations requiring immediate attention"""
        query = """
        SELECT 
            hostname,
            platform,
            environment,
            control_id,
            control_title,
            severity,
            status,
            detected_date,
            urgency_level,
            EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - detected_date))/86400 as days_open
        FROM critical_violations_summary
        ORDER BY 
            CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 END,
            detected_date
        LIMIT %(limit)s
        """
        
        return self.execute_query(query, {'limit': limit})

    def get_remediation_status(self) -> List[Dict]:
        """Get remediation task status summary"""
        query = """
        SELECT 
            status,
            priority,
            task_count,
            overdue_count,
            avg_execution_hours
        FROM remediation_dashboard
        ORDER BY 
            CASE status 
                WHEN 'failed' THEN 1 
                WHEN 'running' THEN 2 
                WHEN 'pending' THEN 3 
                ELSE 4 
            END,
            CASE priority 
                WHEN 'CRITICAL' THEN 1 
                WHEN 'HIGH' THEN 2 
                WHEN 'MEDIUM' THEN 3 
                WHEN 'LOW' THEN 4 
            END
        """
        
        return self.execute_query(query)

    def get_compliance_trends(self, days: int = 30) -> List[Dict]:
        """Get compliance trends over time"""
        query = """
        SELECT 
            DATE(assessment_date) as assessment_date,
            COUNT(*) as total_assessments,
            COUNT(CASE WHEN is_compliant THEN 1 END) as compliant_count,
            ROUND(AVG(compliance_score), 2) as avg_score,
            SUM(total_violations) as total_violations
        FROM compliance_assessments
        WHERE assessment_date >= CURRENT_DATE - INTERVAL '%(days)s days'
        GROUP BY DATE(assessment_date)
        ORDER BY assessment_date
        """
        
        return self.execute_query(query, {'days': days})

    def get_system_details(self, hostname: Optional[str] = None) -> List[SystemSummary]:
        """Get detailed system compliance information"""
        where_clause = "WHERE s.hostname = %(hostname)s" if hostname else ""
        
        query = f"""
        SELECT 
            s.hostname,
            s.platform,
            s.environment,
            latest_ca.is_compliant,
            latest_ca.compliance_score,
            latest_ca.total_violations,
            latest_ca.assessment_date as last_assessed
        FROM systems s
        LEFT JOIN LATERAL (
            SELECT * 
            FROM compliance_assessments ca 
            WHERE ca.system_id = s.id 
            ORDER BY ca.assessment_date DESC 
            LIMIT 1
        ) latest_ca ON true
        {where_clause}
        ORDER BY s.hostname
        """
        
        params = {'hostname': hostname} if hostname else {}
        results = self.execute_query(query, params)
        
        return [
            SystemSummary(
                hostname=row['hostname'],
                platform=row['platform'],
                environment=row['environment'],
                is_compliant=row['is_compliant'] or False,
                compliance_score=float(row['compliance_score'] or 0),
                total_violations=row['total_violations'] or 0,
                last_assessed=row['last_assessed'] or datetime.now()
            )
            for row in results
        ]

    def generate_executive_report(self) -> Dict[str, Any]:
        """Generate comprehensive executive report"""
        logger.info("Generating executive compliance report")
        
        report = {
            'generated_at': datetime.now().isoformat(),
            'report_period': '30 days',
            'executive_summary': self.get_executive_summary(),
            'platform_breakdown': self.get_platform_breakdown(),
            'critical_violations': self.get_critical_violations(limit=20),
            'remediation_status': self.get_remediation_status(),
            'compliance_trends': self.get_compliance_trends(30)
        }
        
        return report

    def generate_technical_report(self) -> Dict[str, Any]:
        """Generate detailed technical report"""
        logger.info("Generating technical compliance report")
        
        report = {
            'generated_at': datetime.now().isoformat(),
            'system_details': [asdict(s) for s in self.get_system_details()],
            'critical_violations': self.get_critical_violations(limit=100),
            'platform_breakdown': self.get_platform_breakdown(),
            'remediation_status': self.get_remediation_status()
        }
        
        return report

    def create_compliance_charts(self, output_dir: str = "reports"):
        """Generate compliance visualization charts"""
        logger.info("Creating compliance visualization charts")
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Executive summary chart
        summary = self.get_executive_summary()
        
        environments = list(summary.keys())
        compliance_percentages = [summary[env].compliance_percentage for env in environments]
        total_systems = [summary[env].total_systems for env in environments]
        
        # Compliance by environment
        fig1 = px.bar(
            x=environments,
            y=compliance_percentages,
            title="Compliance Percentage by Environment",
            labels={'x': 'Environment', 'y': 'Compliance %'},
            color=compliance_percentages,
            color_continuous_scale='RdYlGn'
        )
        fig1.write_html(f"{output_dir}/compliance_by_environment.html")
        
        # Violation severity distribution
        all_violations = []
        for env, metrics in summary.items():
            all_violations.extend([
                {'Environment': env, 'Severity': 'CRITICAL', 'Count': metrics.critical_violations},
                {'Environment': env, 'Severity': 'HIGH', 'Count': metrics.high_violations},
                {'Environment': env, 'Severity': 'MEDIUM', 'Count': metrics.medium_violations},
                {'Environment': env, 'Severity': 'LOW', 'Count': metrics.low_violations}
            ])
        
        df_violations = pd.DataFrame(all_violations)
        fig2 = px.bar(
            df_violations,
            x='Environment',
            y='Count',
            color='Severity',
            title="Violation Distribution by Severity",
            color_discrete_map={
                'CRITICAL': '#FF0000',
                'HIGH': '#FF6600',
                'MEDIUM': '#FFCC00',
                'LOW': '#00FF00'
            }
        )
        fig2.write_html(f"{output_dir}/violations_by_severity.html")
        
        # Compliance trends
        trends = self.get_compliance_trends(30)
        if trends:
            df_trends = pd.DataFrame(trends)
            fig3 = px.line(
                df_trends,
                x='assessment_date',
                y='avg_score',
                title="Compliance Score Trends (30 Days)",
                labels={'assessment_date': 'Date', 'avg_score': 'Average Compliance Score'}
            )
            fig3.write_html(f"{output_dir}/compliance_trends.html")
        
        logger.info(f"Charts saved to {output_dir}")

    def export_to_json(self, report_type: str = "executive", filename: Optional[str] = None) -> str:
        """Export report to JSON format"""
        if report_type == "executive":
            report = self.generate_executive_report()
        else:
            report = self.generate_technical_report()
            
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"compliance_report_{report_type}_{timestamp}.json"
            
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2, default=str)
            
        logger.info(f"Report exported to {filename}")
        return filename

    def export_to_csv(self, output_dir: str = "reports") -> List[str]:
        """Export key data to CSV files"""
        os.makedirs(output_dir, exist_ok=True)
        files_created = []
        
        # Systems summary
        systems = self.get_system_details()
        df_systems = pd.DataFrame([asdict(s) for s in systems])
        systems_file = f"{output_dir}/systems_summary.csv"
        df_systems.to_csv(systems_file, index=False)
        files_created.append(systems_file)
        
        # Critical violations
        violations = self.get_critical_violations(limit=1000)
        df_violations = pd.DataFrame(violations)
        violations_file = f"{output_dir}/critical_violations.csv"
        df_violations.to_csv(violations_file, index=False)
        files_created.append(violations_file)
        
        # Platform breakdown
        platforms = self.get_platform_breakdown()
        df_platforms = pd.DataFrame(platforms)
        platforms_file = f"{output_dir}/platform_breakdown.csv"
        df_platforms.to_csv(platforms_file, index=False)
        files_created.append(platforms_file)
        
        logger.info(f"CSV files created: {files_created}")
        return files_created

def load_config() -> Dict[str, Any]:
    """Load configuration from environment variables or config file"""
    config = {
        'database': {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'database': os.getenv('DB_NAME', 'compliance'),
            'user': os.getenv('DB_USER', 'compliance_user'),
            'password': os.getenv('DB_PASSWORD', '')
        }
    }
    
    # Try to load from config file if it exists
    config_file = os.getenv('CONFIG_FILE', 'config.json')
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            file_config = json.load(f)
            config.update(file_config)
    
    return config

def main():
    """Main function for CLI usage"""
    parser = argparse.ArgumentParser(description="Compliance Dashboard and Reporting")
    parser.add_argument('command', choices=['executive', 'technical', 'charts', 'export'], 
                       help='Report type to generate')
    parser.add_argument('--format', choices=['json', 'csv', 'html'], default='json',
                       help='Output format')
    parser.add_argument('--output', help='Output directory or filename')
    parser.add_argument('--hostname', help='Specific hostname for detailed report')
    parser.add_argument('--days', type=int, default=30, help='Number of days for trends')
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config()
    
    # Initialize dashboard
    dashboard = ComplianceDashboard(config['database'])
    
    try:
        dashboard.connect_database()
        
        if args.command == 'executive':
            report = dashboard.generate_executive_report()
            if args.format == 'json':
                filename = dashboard.export_to_json('executive', args.output)
                print(f"Executive report generated: {filename}")
            else:
                print(json.dumps(report, indent=2, default=str))
                
        elif args.command == 'technical':
            report = dashboard.generate_technical_report()
            if args.format == 'json':
                filename = dashboard.export_to_json('technical', args.output)
                print(f"Technical report generated: {filename}")
            else:
                print(json.dumps(report, indent=2, default=str))
                
        elif args.command == 'charts':
            output_dir = args.output or 'reports'
            dashboard.create_compliance_charts(output_dir)
            print(f"Charts generated in {output_dir}")
            
        elif args.command == 'export':
            if args.format == 'csv':
                output_dir = args.output or 'reports'
                files = dashboard.export_to_csv(output_dir)
                print(f"CSV files exported: {files}")
            else:
                filename = dashboard.export_to_json('executive', args.output)
                print(f"Report exported: {filename}")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
    finally:
        dashboard.close_database()

if __name__ == "__main__":
    main()