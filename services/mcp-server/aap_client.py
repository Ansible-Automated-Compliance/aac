"""
AAP Client - HTTP client for Ansible Automation Platform API
"""
import os
import httpx
from typing import Any, Dict, List, Optional


class AAPClient:
    """Client for interacting with Ansible Automation Platform API."""

    def __init__(self):
        self.base_url = os.getenv("AAP_URL", "https://localhost").rstrip("/")
        self.token = os.getenv("AAP_TOKEN", "")
        self.verify_ssl = os.getenv("AAP_VERIFY_SSL", "false").lower() == "true"
        self.timeout = int(os.getenv("AAP_TIMEOUT", "30"))

        self.client = httpx.Client(
            base_url=f"{self.base_url}/api/controller/v2",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            verify=self.verify_ssl,
            timeout=self.timeout,
        )

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make GET request to AAP API."""
        response = self.client.get(endpoint, params=params)
        response.raise_for_status()
        return response.json()

    def _post(self, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Make POST request to AAP API."""
        response = self.client.post(endpoint, json=data or {})
        response.raise_for_status()
        return response.json()

    # Inventory operations
    def list_inventories(self) -> List[Dict]:
        """List all inventories."""
        result = self._get("/inventories/")
        return result.get("results", [])

    def get_inventory(self, inventory_id: int) -> Dict:
        """Get inventory details."""
        return self._get(f"/inventories/{inventory_id}/")

    def list_hosts(self, inventory_id: int) -> List[Dict]:
        """List hosts in an inventory."""
        result = self._get(f"/inventories/{inventory_id}/hosts/")
        return result.get("results", [])

    def get_host(self, host_id: int) -> Dict:
        """Get host details."""
        return self._get(f"/hosts/{host_id}/")

    # Job template operations
    def list_job_templates(self) -> List[Dict]:
        """List all job templates."""
        result = self._get("/job_templates/")
        return result.get("results", [])

    def get_job_template(self, template_id: int) -> Dict:
        """Get job template details."""
        return self._get(f"/job_templates/{template_id}/")

    def launch_job(self, template_id: int, extra_vars: Optional[Dict] = None) -> Dict:
        """Launch a job from template."""
        data = {}
        if extra_vars:
            data["extra_vars"] = extra_vars
        return self._post(f"/job_templates/{template_id}/launch/", data)

    # Job operations
    def list_jobs(self) -> List[Dict]:
        """List all jobs."""
        result = self._get("/jobs/")
        return result.get("results", [])

    def get_job(self, job_id: int) -> Dict:
        """Get job details."""
        return self._get(f"/jobs/{job_id}/")

    def get_job_stdout(self, job_id: int) -> str:
        """Get job output."""
        response = self.client.get(
            f"/jobs/{job_id}/stdout/",
            params={"format": "txt"},
        )
        response.raise_for_status()
        return response.text

    # Project operations
    def list_projects(self) -> List[Dict]:
        """List all projects."""
        result = self._get("/projects/")
        return result.get("results", [])

    def get_project(self, project_id: int) -> Dict:
        """Get project details."""
        return self._get(f"/projects/{project_id}/")

    def sync_project(self, project_id: int) -> Dict:
        """Trigger project sync."""
        return self._post(f"/projects/{project_id}/update/")

    # Group operations
    def list_groups(self, inventory_id: int) -> List[Dict]:
        """List groups in an inventory."""
        result = self._get(f"/inventories/{inventory_id}/groups/")
        return result.get("results", [])

    def close(self):
        """Close the HTTP client."""
        self.client.close()
