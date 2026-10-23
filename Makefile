# Makefile for OPA CIS/NIST Compliance Policy Testing

.PHONY: help install test test-unit test-integration test-performance validate check-syntax check-accuracy clean setup
.DEFAULT_GOAL := help

# Configuration
OPA_VERSION ?= 1.10.0
PYTHON_VERSION ?= 3.11
TEST_TIMEOUT ?= 300
REPO_ROOT := $(shell pwd)

# Colors for output
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

submodules: ## Initialize/update git submodules (required before lint/test)
	git submodule update --init --recursive

_check-submodules:
	@if [ ! -f policies/Makefile ]; then \
	  echo "$(RED)❌ policies/ submodule not initialized. Run: make submodules$(NC)"; \
	  exit 1; \
	fi

help: ## Show this help message
	@echo "🔧 OPA Policy Testing & Validation Toolkit"
	@echo ""
	@echo "Available commands:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install OPA and Python dependencies
	@echo "📦 Installing dependencies..."
	@if ! command -v opa &> /dev/null; then \
		echo "Installing OPA $(OPA_VERSION)..."; \
		curl -L -o /tmp/opa https://github.com/open-policy-agent/opa/releases/download/v$(OPA_VERSION)/opa_$$(uname -s | tr '[:upper:]' '[:lower:]')_amd64_static; \
		chmod +x /tmp/opa; \
		sudo mv /tmp/opa /usr/local/bin/opa; \
	fi
	@echo "Installing Python dependencies..."
	@pip install pyyaml requests || true
	@echo "  Note: jq must be installed via system package manager (dnf/apt/brew install jq)"
	@echo "$(GREEN)✅ Dependencies installed$(NC)"

setup: install ## Setup development environment
	@echo "🚀 Setting up development environment..."
	@mkdir -p reports logs
	@python scripts/check_policy_accuracy.py --generate-config policy-accuracy-config.json
	@echo "$(GREEN)✅ Development environment ready$(NC)"

check-syntax: _check-submodules ## Validate Rego syntax
	@echo "📝 Checking Rego syntax..."
	@find policies -name "*.rego" -exec opa fmt --diff {} \; || (echo "$(RED)❌ Syntax errors found$(NC)" && exit 1)
	@find tests -name "*.rego" -exec opa fmt --diff {} \; || (echo "$(RED)❌ Syntax errors found in tests$(NC)" && exit 1)
	@echo "$(GREEN)✅ Syntax validation passed$(NC)"

check-compilation: _check-submodules ## Check if policies compile
	@echo "🔍 Checking policy compilation..."
	@opa build policies/ tests/ --output /tmp/policy-bundle.tar.gz || (echo "$(RED)❌ Compilation failed$(NC)" && exit 1)
	@echo "$(GREEN)✅ All policies compile successfully$(NC)"

test-unit: _check-submodules ## Run unit tests
	@echo "🧪 Running unit tests..."
	@if [ -f "tests/unit_tests.rego" ]; then \
		timeout $(TEST_TIMEOUT) opa test policies/ tests/unit_tests.rego tests/comprehensive_test_suite.rego --verbose || (echo "$(RED)❌ Unit tests failed$(NC)" && exit 1); \
	else \
		echo "$(YELLOW)⚠️  No unit tests found$(NC)"; \
	fi
	@echo "$(GREEN)✅ Unit tests passed$(NC)"

test-integration: _check-submodules ## Run integration tests
	@echo "🔗 Running integration tests..."
	@if [ -f "tests/integration_tests.rego" ]; then \
		timeout $(TEST_TIMEOUT) opa test policies/ tests/integration_tests.rego --verbose || (echo "$(RED)❌ Integration tests failed$(NC)" && exit 1); \
	else \
		echo "$(YELLOW)⚠️  No integration tests found$(NC)"; \
	fi

test-performance: ## Run performance tests
	@echo "⚡ Running performance tests..."
	@if [ -f "tests/performance_tests.rego" ]; then \
		timeout $(TEST_TIMEOUT) opa test . tests/performance_tests.rego --verbose || echo "$(YELLOW)⚠️  Performance tests had issues$(NC)"; \
	else \
		echo "$(YELLOW)⚠️  No performance tests found$(NC)"; \
	fi

test: check-syntax check-compilation test-unit test-integration ## Run all tests
	@echo "$(GREEN)🎉 All tests completed$(NC)"

validate: ## Run policy validation scripts
	@echo "✅ Running policy validation..."
	@python scripts/validate_policies.py --verbose --output reports/validation-report.json || (echo "$(RED)❌ Validation failed$(NC)" && exit 1)
	@echo "$(GREEN)✅ Policy validation passed$(NC)"

check-accuracy: ## Check policy accuracy against standards
	@echo "🎯 Checking policy accuracy..."
	@python scripts/check_policy_accuracy.py --verbose --output reports/accuracy-report.json || (echo "$(RED)❌ Accuracy check failed$(NC)" && exit 1)
	@echo "$(GREEN)✅ Accuracy check passed$(NC)"

generate-test-data: ## Generate test data using Python script
	@echo "🗃️  Generating test data..."
	@python tests/test_data_generator.py --output-dir tests/generated_data/
	@echo "$(GREEN)✅ Test data generated$(NC)"

benchmark: ## Run policy benchmarks
	@echo "📊 Running policy benchmarks..."
	@python -c "
	import time
	import subprocess
	import json
	from pathlib import Path
	
	results = {'benchmark_date': time.strftime('%Y-%m-%d %H:%M:%S'), 'tests': []}
	
	test_files = list(Path('tests').glob('*.rego'))
	for test_file in test_files:
	    start_time = time.time()
	    try:
	        result = subprocess.run(['opa', 'test', '.', str(test_file)], 
	                              capture_output=True, text=True, timeout=60)
	        duration = time.time() - start_time
	        results['tests'].append({
	            'file': str(test_file),
	            'duration': duration,
	            'passed': result.returncode == 0
	        })
	        print(f'📈 {test_file.name}: {duration:.2f}s')
	    except subprocess.TimeoutExpired:
	        print(f'⏰ {test_file.name}: TIMEOUT')
	        results['tests'].append({
	            'file': str(test_file),
	            'duration': 60,
	            'passed': False,
	            'timeout': True
	        })
	
	with open('reports/benchmark-results.json', 'w') as f:
	    json.dump(results, f, indent=2)
	"
	@echo "$(GREEN)✅ Benchmark completed$(NC)"

security-check: ## Run security analysis on policies
	@echo "🔒 Running security analysis..."
	@echo "Checking for potential security issues..."
	@if grep -r "allow.*true" policies/ --include="*.rego" 2>/dev/null; then \
		echo "$(YELLOW)⚠️  Found unconditional allow rules$(NC)"; \
	fi
	@if grep -r -i "password\|secret\|key.*=" policies/ --include="*.rego" 2>/dev/null; then \
		echo "$(RED)🚨 Found potential hardcoded credentials$(NC)"; \
		exit 1; \
	fi
	@python scripts/check_policy_accuracy.py --check thresholds --verbose
	@echo "$(GREEN)✅ Security analysis completed$(NC)"

coverage: ## Generate test coverage report
	@echo "📊 Generating test coverage report..."
	@python -c "
	import json
	from pathlib import Path
	
	policy_files = list(Path('policies').rglob('*.rego'))
	test_files = list(Path('tests').rglob('*.rego'))
	
	# Extract package names from policies
	policy_packages = set()
	for pf in policy_files:
	    with open(pf) as f:
	        for line in f:
	            if line.strip().startswith('package '):
	                pkg = line.split('package ')[1].strip()
	                if not pkg.startswith('tests'):
	                    policy_packages.add(pkg)
	                break
	
	# Extract tested packages from tests
	tested_packages = set()
	for tf in test_files:
	    with open(tf) as f:
	        for line in f:
	            if 'import data.' in line:
	                imported = line.split('import data.')[1].split()[0].strip()
	                tested_packages.add(imported)
	
	coverage_pct = len(tested_packages) / len(policy_packages) * 100 if policy_packages else 0
	
	report = {
	    'total_policies': len(policy_packages),
	    'tested_policies': len(tested_packages),
	    'coverage_percentage': coverage_pct,
	    'untested_packages': list(policy_packages - tested_packages)
	}
	
	with open('reports/coverage-report.json', 'w') as f:
	    json.dump(report, f, indent=2)
	
	print(f'📊 Test Coverage: {coverage_pct:.1f}%')
	print(f'📈 Tested Packages: {len(tested_packages)}/{len(policy_packages)}')
	"
	@echo "$(GREEN)✅ Coverage report generated$(NC)"

full-check: test validate check-accuracy security-check coverage benchmark ## Run comprehensive validation
	@echo "$(GREEN)🏆 Full validation completed successfully$(NC)"

clean: ## Clean generated files and reports
	@echo "🧹 Cleaning up..."
	@rm -rf reports/*.json logs/*.log tests/generated_data/
	@rm -f policy-bundle.tar.gz policy-accuracy-config.json
	@echo "$(GREEN)✅ Cleanup completed$(NC)"

watch: ## Watch for changes and run tests
	@echo "👀 Watching for file changes..."
	@if command -v fswatch &> /dev/null; then \
		fswatch -o policies/ tests/ | xargs -n1 -I{} make test-unit; \
	elif command -v inotifywait &> /dev/null; then \
		while inotifywait -r -e modify policies/ tests/; do make test-unit; done; \
	else \
		echo "$(YELLOW)⚠️  Install fswatch or inotify-tools for file watching$(NC)"; \
	fi

serve-docs: ## Serve documentation locally
	@echo "📚 Starting documentation server..."
	@if command -v python3 &> /dev/null; then \
		cd docs && python3 -m http.server 8000; \
	else \
		echo "$(RED)❌ Python 3 not found$(NC)"; \
	fi

init-pre-commit: ## Initialize pre-commit hooks
	@echo "🪝 Setting up pre-commit hooks..."
	@cat > .git/hooks/pre-commit << 'EOF'
#!/bin/bash
echo "🔍 Running pre-commit validation..."
make check-syntax check-accuracy
if [ $$? -ne 0 ]; then
    echo "❌ Pre-commit validation failed"
    exit 1
fi
echo "✅ Pre-commit validation passed"
EOF
	@chmod +x .git/hooks/pre-commit
	@echo "$(GREEN)✅ Pre-commit hooks installed$(NC)"

stats: ## Show repository statistics
	@echo "📊 Repository Statistics"
	@echo "========================"
	@echo "Policy files: $$(find policies -name '*.rego' | wc -l)"
	@echo "Test files: $$(find tests -name '*.rego' | wc -l)"
	@echo "Total lines of Rego: $$(find . -name '*.rego' -exec wc -l {} + | tail -1 | awk '{print $$1}')"
	@echo "Python scripts: $$(find scripts -name '*.py' | wc -l)"
	@echo "Documentation files: $$(find . -name '*.md' | wc -l)"

# Compliance reporting targets
report: ## Generate comprehensive compliance report (HTML)
	@echo "📊 Generating comprehensive compliance report..."
	@python scripts/compliance_reporter.py --sample-data --output-format html
	@echo "$(GREEN)✅ Compliance report generated$(NC)"

report-json: ## Generate compliance report in JSON format
	@echo "📊 Generating JSON compliance report..."
	@python scripts/compliance_reporter.py --sample-data --output-format json
	@echo "$(GREEN)✅ JSON report generated$(NC)"

report-csv: ## Generate compliance report in CSV format
	@echo "📊 Generating CSV compliance report..."
	@python scripts/compliance_reporter.py --sample-data --output-format csv
	@echo "$(GREEN)✅ CSV report generated$(NC)"

report-cis: ## Generate CIS-only compliance report
	@echo "📊 Generating CIS compliance report..."
	@python scripts/compliance_reporter.py --sample-data --frameworks cis --output-format html
	@echo "$(GREEN)✅ CIS report generated$(NC)"

report-nist: ## Generate NIST-only compliance report
	@echo "📊 Generating NIST compliance report..."
	@python scripts/compliance_reporter.py --sample-data --frameworks nist_csf nist_sp800_53 nist_sp800_171 nist_rmf --output-format html
	@echo "$(GREEN)✅ NIST report generated$(NC)"

report-iso27001: ## Generate ISO 27001 compliance report
	@echo "📊 Generating ISO 27001 compliance report..."
	@python scripts/compliance_reporter.py --sample-data --frameworks iso27001 --output-format html
	@echo "$(GREEN)✅ ISO 27001 report generated$(NC)"

report-with-data: ## Generate report with custom input data file
	@if [ -z "$(INPUT_FILE)" ]; then \
		echo "$(RED)❌ Please specify INPUT_FILE=path/to/data.json$(NC)"; \
		exit 1; \
	fi
	@echo "📊 Generating compliance report with $(INPUT_FILE)..."
	@python scripts/compliance_reporter.py --input-file $(INPUT_FILE) --output-format html
	@echo "$(GREEN)✅ Custom report generated$(NC)"

compliance-dashboard: ## Open compliance reports in browser
	@echo "🌐 Opening compliance dashboard..."
	@if [ -d "reports" ]; then \
		LATEST_REPORT=$$(ls -t reports/*.html 2>/dev/null | head -1); \
		if [ -n "$$LATEST_REPORT" ]; then \
			echo "Opening $$LATEST_REPORT"; \
			if command -v open >/dev/null 2>&1; then \
				open "$$LATEST_REPORT"; \
			elif command -v xdg-open >/dev/null 2>&1; then \
				xdg-open "$$LATEST_REPORT"; \
			else \
				echo "Please open $$LATEST_REPORT in your browser"; \
			fi; \
		else \
			echo "$(YELLOW)⚠️  No HTML reports found. Run 'make report' first.$(NC)"; \
		fi; \
	else \
		echo "$(YELLOW)⚠️  Reports directory not found. Run 'make report' first.$(NC)"; \
	fi

# Development helpers
dev-setup: setup init-pre-commit ## Complete development setup
	@echo "$(GREEN)🚀 Development environment fully configured$(NC)"

quick-test: check-syntax test-unit ## Quick test for development
	@echo "$(GREEN)⚡ Quick test completed$(NC)"

# CI/CD helpers  
ci-test: install test validate check-accuracy ## CI/CD test pipeline
	@echo "$(GREEN)🤖 CI test pipeline completed$(NC)"