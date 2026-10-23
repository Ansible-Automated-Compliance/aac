#!/usr/bin/env python3
"""
Documentation Validation Tool for OPA Compliance Policies

This tool validates that documentation is comprehensive, accurate, and
up-to-date across all policy files, README files, and supporting documentation.
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Any, Tuple
import argparse
import markdown
from urllib.parse import urlparse
import requests
import time

class DocumentationValidator:
    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root)
        self.policies_dir = self.repo_root / "policies"
        self.tests_dir = self.repo_root / "tests"
        self.docs_dir = self.repo_root / "docs"
        self.scripts_dir = self.repo_root / "scripts"
        self.validation_issues = []
        
        # Documentation requirements
        self.required_sections = [
            "description", "overview", "installation", "usage", "examples",
            "testing", "contributing", "license"
        ]
        
        self.code_quality_patterns = {
            "TODO": r"TODO|FIXME|XXX|HACK",
            "debug_prints": r"print\(|console\.log\(|debugger",
            "hardcoded_values": r"password\s*=\s*[\"'][^\"']+[\"']|api_key\s*=\s*[\"'][^\"']+[\"']",
            "commented_code": r"^\s*#\s*(def |class |import |from )"
        }
    
    def validate_readme_completeness(self) -> bool:
        """Validate that README files are comprehensive"""
        readme_files = list(self.repo_root.glob("README.md")) + list(self.repo_root.glob("readme.md"))
        
        if not readme_files:
            self.validation_issues.append("No README.md file found in repository root")
            return False
        
        readme_file = readme_files[0]
        
        try:
            with open(readme_file, 'r', encoding='utf-8') as f:
                content = f.read().lower()
            
            missing_sections = []
            for section in self.required_sections:
                if section not in content:
                    missing_sections.append(section)
            
            if missing_sections:
                self.validation_issues.append(f"README missing sections: {', '.join(missing_sections)}")
            
            # Check for basic content requirements
            requirements = {
                "badges": r"!\[.*\]\(.*\)",
                "installation_commands": r"`.*install.*`|```.*install.*```",
                "usage_examples": r"```.*```",
                "links": r"\[.*\]\(.*\)"
            }
            
            missing_content = []
            for req_name, pattern in requirements.items():
                if not re.search(pattern, content, re.IGNORECASE | re.DOTALL):
                    missing_content.append(req_name)
            
            if missing_content:
                self.validation_issues.append(f"README missing content: {', '.join(missing_content)}")
            
            return len(missing_sections) == 0 and len(missing_content) == 0
            
        except Exception as e:
            self.validation_issues.append(f"Error reading README: {e}")
            return False
    
    def validate_policy_documentation(self) -> bool:
        """Validate that policy files have adequate documentation"""
        policy_files = list(self.policies_dir.rglob("*.rego"))
        poorly_documented = []
        missing_headers = []
        
        for policy_file in policy_files:
            try:
                with open(policy_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                lines = content.split('\n')
                comment_lines = [line for line in lines if line.strip().startswith('#')]
                code_lines = [line for line in lines if line.strip() and not line.strip().startswith('#')]
                
                # Check comment ratio
                if len(code_lines) > 0:
                    comment_ratio = len(comment_lines) / len(code_lines)
                    if comment_ratio < 0.15:  # Less than 15% comments
                        poorly_documented.append(str(policy_file.relative_to(self.repo_root)))
                
                # Check for file header documentation
                header_found = False
                for line in lines[:10]:  # Check first 10 lines
                    if any(keyword in line.lower() for keyword in 
                          ['cis', 'nist', 'benchmark', 'standard', 'control', 'policy']):
                        header_found = True
                        break
                
                if not header_found:
                    missing_headers.append(str(policy_file.relative_to(self.repo_root)))
                    
            except Exception as e:
                self.validation_issues.append(f"Error reading {policy_file}: {e}")
        
        if poorly_documented:
            self.validation_issues.append(f"Policies with insufficient comments: {poorly_documented[:5]}")
        
        if missing_headers:
            self.validation_issues.append(f"Policies missing descriptive headers: {missing_headers[:5]}")
        
        return len(poorly_documented) == 0 and len(missing_headers) == 0
    
    def validate_inline_documentation(self) -> bool:
        """Validate inline documentation quality"""
        all_files = (
            list(self.policies_dir.rglob("*.rego")) + 
            list(self.tests_dir.rglob("*.rego")) +
            list(self.scripts_dir.rglob("*.py"))
        )
        
        documentation_issues = []
        
        for file_path in all_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Check for quality issues
                for issue_type, pattern in self.code_quality_patterns.items():
                    matches = re.findall(pattern, content, re.MULTILINE | re.IGNORECASE)
                    if matches:
                        documentation_issues.append(f"{file_path.name}: {issue_type} ({len(matches)} instances)")
                
                # Check for proper function/rule documentation
                if file_path.suffix == '.rego':
                    # Find rule definitions without documentation
                    rule_pattern = r'^(\w+)\s*{'
                    rules = re.findall(rule_pattern, content, re.MULTILINE)
                    
                    for rule in rules:
                        # Look for comment above rule
                        rule_line_pattern = f'^{re.escape(rule)}\\s*{{'
                        match = re.search(rule_line_pattern, content, re.MULTILINE)
                        if match:
                            lines_before = content[:match.start()].split('\n')
                            # Check if there's a comment in the 3 lines before
                            has_doc = False
                            for line in lines_before[-3:]:
                                if line.strip().startswith('#') and len(line.strip()) > 5:
                                    has_doc = True
                                    break
                            
                            if not has_doc:
                                documentation_issues.append(f"{file_path.name}: Rule '{rule}' lacks documentation")
                
                elif file_path.suffix == '.py':
                    # Check for function documentation
                    function_pattern = r'^def\s+(\w+)\('
                    functions = re.findall(function_pattern, content, re.MULTILINE)
                    
                    for func in functions:
                        if not func.startswith('_'):  # Skip private functions
                            func_line_pattern = f'^def\\s+{re.escape(func)}\\('
                            match = re.search(func_line_pattern, content, re.MULTILINE)
                            if match:
                                # Look for docstring
                                after_def = content[match.end():]
                                lines_after = after_def.split('\n')
                                has_docstring = False
                                for line in lines_after[:5]:
                                    if '"""' in line or "'''" in line:
                                        has_docstring = True
                                        break
                                
                                if not has_docstring:
                                    documentation_issues.append(f"{file_path.name}: Function '{func}' lacks docstring")
                
            except Exception as e:
                self.validation_issues.append(f"Error analyzing {file_path}: {e}")
        
        if documentation_issues:
            self.validation_issues.extend(documentation_issues[:10])  # Limit to first 10
            return False
        return True
    
    def validate_markdown_files(self) -> bool:
        """Validate markdown files for syntax and content"""
        markdown_files = list(self.repo_root.rglob("*.md"))
        markdown_issues = []
        
        for md_file in markdown_files:
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Try to parse markdown
                try:
                    markdown.markdown(content)
                except Exception as e:
                    markdown_issues.append(f"{md_file.name}: Markdown syntax error - {e}")
                
                # Check for broken internal links
                link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
                links = re.findall(link_pattern, content)
                
                for link_text, link_url in links:
                    # Skip external URLs
                    if link_url.startswith(('http://', 'https://', 'mailto:')):
                        continue
                    
                    # Check internal file links
                    if not link_url.startswith('#'):  # Skip anchor links
                        target_path = md_file.parent / link_url
                        if not target_path.exists():
                            markdown_issues.append(f"{md_file.name}: Broken internal link - {link_url}")
                
                # Check for empty sections
                section_pattern = r'^#+\s+(.+)$'
                sections = re.findall(section_pattern, content, re.MULTILINE)
                
                for i, section in enumerate(sections):
                    # Find content between this section and next
                    section_regex = f'^#+\\s+{re.escape(section)}\\s*$'
                    section_match = re.search(section_regex, content, re.MULTILINE)
                    
                    if section_match:
                        after_section = content[section_match.end():]
                        if i < len(sections) - 1:
                            next_section_regex = f'^#+\\s+{re.escape(sections[i+1])}\\s*$'
                            next_match = re.search(next_section_regex, after_section, re.MULTILINE)
                            if next_match:
                                section_content = after_section[:next_match.start()]
                            else:
                                section_content = after_section
                        else:
                            section_content = after_section
                        
                        # Check if section has meaningful content
                        content_lines = [line.strip() for line in section_content.split('\n') if line.strip()]
                        if len(content_lines) < 2:
                            markdown_issues.append(f"{md_file.name}: Empty or minimal section - {section}")
                
            except Exception as e:
                markdown_issues.append(f"{md_file.name}: Error reading file - {e}")
        
        if markdown_issues:
            self.validation_issues.extend(markdown_issues[:15])  # Limit to first 15
            return False
        return True
    
    def validate_external_links(self, timeout: int = 5) -> bool:
        """Validate external links in documentation"""
        markdown_files = list(self.repo_root.rglob("*.md"))
        broken_links = []
        
        all_external_links = set()
        
        for md_file in markdown_files:
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Find external links
                link_pattern = r'\[([^\]]+)\]\((https?://[^)]+)\)'
                links = re.findall(link_pattern, content)
                
                for link_text, link_url in links:
                    all_external_links.add((link_url, f"{md_file.name}"))
                    
            except Exception:
                continue
        
        # Check each unique external link
        for link_url, source_file in all_external_links:
            try:
                response = requests.head(link_url, timeout=timeout, allow_redirects=True)
                if response.status_code >= 400:
                    broken_links.append(f"{source_file}: {link_url} (Status: {response.status_code})")
            except requests.RequestException as e:
                broken_links.append(f"{source_file}: {link_url} (Error: {str(e)[:50]})")
            
            # Be nice to servers
            time.sleep(0.5)
        
        if broken_links:
            self.validation_issues.extend(broken_links[:10])  # Limit to first 10
            return False
        return True
    
    def validate_code_examples(self) -> bool:
        """Validate code examples in documentation"""
        markdown_files = list(self.repo_root.rglob("*.md"))
        code_issues = []
        
        for md_file in markdown_files:
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Find code blocks
                code_block_pattern = r'```(\w+)?\n(.*?)```'
                code_blocks = re.findall(code_block_pattern, content, re.DOTALL)
                
                for lang, code in code_blocks:
                    if lang.lower() in ['bash', 'shell', 'sh']:
                        # Validate bash commands
                        lines = code.strip().split('\n')
                        for line in lines:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                # Check for dangerous commands
                                dangerous_patterns = [
                                    r'rm\s+-rf\s+/',
                                    r'sudo\s+rm',
                                    r'>(>?)\s*/dev/',
                                    r'dd\s+if='
                                ]
                                
                                for pattern in dangerous_patterns:
                                    if re.search(pattern, line):
                                        code_issues.append(f"{md_file.name}: Potentially dangerous bash command - {line[:50]}")
                    
                    elif lang.lower() in ['rego']:
                        # Basic Rego syntax validation
                        if 'package ' not in code:
                            code_issues.append(f"{md_file.name}: Rego example missing package declaration")
                        
                        # Check for common syntax errors
                        if re.search(r'{\s*$.*?^\s*}', code, re.MULTILINE | re.DOTALL):
                            # Has rule structure, check for basic issues
                            if not re.search(r'\w+\s*{', code):
                                code_issues.append(f"{md_file.name}: Rego example has malformed rule")
                    
                    elif lang.lower() in ['json', 'yaml', 'yml']:
                        # Validate JSON/YAML syntax
                        try:
                            if lang.lower() == 'json':
                                json.loads(code)
                            else:
                                import yaml
                                yaml.safe_load(code)
                        except Exception as e:
                            code_issues.append(f"{md_file.name}: Invalid {lang} syntax - {str(e)[:50]}")
                
            except Exception as e:
                code_issues.append(f"{md_file.name}: Error validating code examples - {e}")
        
        if code_issues:
            self.validation_issues.extend(code_issues[:10])
            return False
        return True
    
    def validate_documentation_consistency(self) -> bool:
        """Validate consistency between documentation and code"""
        consistency_issues = []
        
        # Check if documented features exist in code
        readme_file = self.repo_root / "README.md"
        if readme_file.exists():
            try:
                with open(readme_file, 'r', encoding='utf-8') as f:
                    readme_content = f.read()
                
                # Find mentioned scripts/tools
                script_pattern = r'`([^`]+\.py|[^`]+\.sh)`'
                mentioned_scripts = re.findall(script_pattern, readme_content)
                
                for script in mentioned_scripts:
                    script_path = self.repo_root / script
                    if not script_path.exists():
                        # Try in scripts directory
                        script_path = self.scripts_dir / script
                        if not script_path.exists():
                            consistency_issues.append(f"README mentions non-existent script: {script}")
                
                # Find mentioned configuration files
                config_pattern = r'`([^`]+\.json|[^`]+\.yaml|[^`]+\.yml|[^`]+\.conf)`'
                mentioned_configs = re.findall(config_pattern, readme_content)
                
                for config in mentioned_configs:
                    config_path = self.repo_root / config
                    if not config_path.exists():
                        # Try in config directory
                        config_path = self.repo_root / "config" / config
                        if not config_path.exists():
                            consistency_issues.append(f"README mentions non-existent config: {config}")
                
            except Exception as e:
                consistency_issues.append(f"Error checking README consistency: {e}")
        
        # Check if all major scripts are documented
        script_files = list(self.scripts_dir.glob("*.py")) if self.scripts_dir.exists() else []
        for script_file in script_files:
            if script_file.name not in readme_content if readme_file.exists() else True:
                consistency_issues.append(f"Script {script_file.name} not documented in README")
        
        if consistency_issues:
            self.validation_issues.extend(consistency_issues)
            return False
        return True
    
    def generate_documentation_report(self) -> Dict[str, Any]:
        """Generate comprehensive documentation validation report"""
        validations = [
            ("README Completeness", self.validate_readme_completeness),
            ("Policy Documentation", self.validate_policy_documentation),
            ("Inline Documentation", self.validate_inline_documentation),
            ("Markdown Files", self.validate_markdown_files),
            ("Code Examples", self.validate_code_examples),
            ("Documentation Consistency", self.validate_documentation_consistency)
        ]
        
        # Skip external link validation by default (can be slow)
        # ("External Links", self.validate_external_links),
        
        results = {}
        overall_passed = True
        
        for validation_name, validation_func in validations:
            try:
                result = validation_func()
                results[validation_name] = {
                    "passed": result,
                    "issues": [issue for issue in self.validation_issues 
                              if validation_name.lower().replace(' ', '_') in issue.lower()]
                }
                overall_passed = overall_passed and result
            except Exception as e:
                results[validation_name] = {
                    "passed": False,
                    "issues": [f"Validation failed with error: {e}"]
                }
                overall_passed = False
        
        # Calculate documentation metrics
        policy_files = list(self.policies_dir.rglob("*.rego")) if self.policies_dir.exists() else []
        markdown_files = list(self.repo_root.rglob("*.md"))
        python_files = list(self.scripts_dir.rglob("*.py")) if self.scripts_dir.exists() else []
        
        return {
            "overall_passed": overall_passed,
            "total_issues": len(self.validation_issues),
            "validation_results": results,
            "all_issues": self.validation_issues,
            "documentation_metrics": {
                "total_policy_files": len(policy_files),
                "total_markdown_files": len(markdown_files),
                "total_python_files": len(python_files),
                "has_readme": (self.repo_root / "README.md").exists(),
                "has_contributing": (self.repo_root / "CONTRIBUTING.md").exists(),
                "has_license": any((self.repo_root / name).exists() for name in ["LICENSE", "LICENSE.md", "LICENSE.txt"])
            },
            "summary": {
                "validations_passed": sum(1 for r in results.values() if r["passed"]),
                "total_validations": len(results),
                "documentation_score": sum(1 for r in results.values() if r["passed"]) / len(results) * 100 if results else 0
            }
        }

def main():
    parser = argparse.ArgumentParser(description="Validate documentation quality and completeness")
    parser.add_argument("--repo-root", default=".", help="Repository root directory")
    parser.add_argument("--output", help="Output file for documentation report (JSON)")
    parser.add_argument("--check-external-links", action="store_true", help="Check external links (slow)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--check", choices=["readme", "policies", "markdown", "examples"], help="Run specific check only")
    
    args = parser.parse_args()
    
    validator = DocumentationValidator(args.repo_root)
    
    print("📚 Starting documentation validation...")
    
    if args.check:
        if args.check == "readme":
            result = validator.validate_readme_completeness()
        elif args.check == "policies":
            result = validator.validate_policy_documentation()
        elif args.check == "markdown":
            result = validator.validate_markdown_files()
        elif args.check == "examples":
            result = validator.validate_code_examples()
        
        print(f"✅ {args.check.title()} validation: {'PASSED' if result else 'FAILED'}")
        if args.verbose and validator.validation_issues:
            for issue in validator.validation_issues:
                print(f"  • {issue}")
    else:
        if args.check_external_links:
            print("🔗 Including external link validation (this may take a while)...")
        
        report = validator.generate_documentation_report()
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(report, f, indent=2)
            print(f"📄 Documentation report saved to {args.output}")
        
        # Print summary
        print("\n" + "="*60)
        print("📊 DOCUMENTATION VALIDATION SUMMARY")
        print("="*60)
        print(f"Overall Status: {'✅ PASSED' if report['overall_passed'] else '❌ FAILED'}")
        print(f"Documentation Score: {report['summary']['documentation_score']:.1f}%")
        print(f"Validations Passed: {report['summary']['validations_passed']}/{report['summary']['total_validations']}")
        print(f"Total Issues: {report['total_issues']}")
        
        metrics = report["documentation_metrics"]
        print(f"\n📈 Documentation Metrics:")
        print(f"  • Policy Files: {metrics['total_policy_files']}")
        print(f"  • Markdown Files: {metrics['total_markdown_files']}")
        print(f"  • Python Files: {metrics['total_python_files']}")
        print(f"  • Has README: {'✅' if metrics['has_readme'] else '❌'}")
        print(f"  • Has Contributing Guide: {'✅' if metrics['has_contributing'] else '❌'}")
        print(f"  • Has License: {'✅' if metrics['has_license'] else '❌'}")
        
        if args.verbose and report['all_issues']:
            print(f"\n🚨 DOCUMENTATION ISSUES:")
            for issue in report['all_issues'][:15]:  # Show first 15
                print(f"  • {issue}")
            if len(report['all_issues']) > 15:
                print(f"  ... and {len(report['all_issues']) - 15} more issues")
    
    return 0 if (not args.check and report.get('overall_passed', False)) or (args.check and result) else 1

if __name__ == "__main__":
    sys.exit(main())