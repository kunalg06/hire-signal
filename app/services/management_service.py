"""System management service for Docker and application lifecycle.

Docker operations go through the `docker` CLI via subprocess, not the
docker-py SDK — see docker_service.py's module docstring for why
(docker==7.0.0 is incompatible with modern requests/urllib3, raising
"Not supported URL scheme http+docker"). This mirrors that module's
_run()/inspect-based pattern rather than importing docker-py here too.
"""

import json
import logging
import subprocess
from typing import Dict, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _run(args: List[str], check=True, capture=True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['docker'] + args,
        capture_output=capture,
        text=True,
        check=check,
    )


class ManagementService:
    """Manage application lifecycle, Docker services, and system health"""

    @staticmethod
    def _docker_available() -> bool:
        """True if the docker CLI/daemon is reachable, without raising."""
        try:
            _run(['info'], check=True)
            return True
        except Exception as e:
            logger.error("Could not connect to Docker: %s", e)
            return False

    @staticmethod
    def _list_containers(all_containers: bool = False, name_filter: str = None) -> List[Dict]:
        """List containers as dicts (one `docker inspect` per match) — used
        instead of parsing `docker ps` table/JSON output, whose CreatedAt
        and Ports fields are human-formatted strings rather than the
        structured data the rest of this module expects."""
        args = ['ps', '-q']
        if all_containers:
            args.insert(1, '-a')
        if name_filter:
            args += ['--filter', f'name={name_filter}']

        ids = [line for line in _run(args, check=True).stdout.strip().splitlines() if line]
        if not ids:
            return []

        inspect_out = _run(['inspect'] + ids, check=True).stdout
        return json.loads(inspect_out)

    @staticmethod
    def get_system_status() -> Dict:
        """Get current system status"""
        status = {
            "timestamp": datetime.now().isoformat(),
            "status": "unknown",
            "services": {},
            "containers": {},
            "errors": []
        }

        if not ManagementService._docker_available():
            status["status"] = "error"
            status["errors"].append("Docker daemon not accessible")
            return status

        status["services"]["docker"] = "running"

        try:
            all_running = ManagementService._list_containers()
            assignment_containers = [
                c for c in all_running if 'assignment' in c.get('Name', '')
            ]

            status["containers"]["total_running"] = len(all_running)
            status["containers"]["assignment_containers"] = len(assignment_containers)
            status["containers"]["containers"] = [
                {
                    "id": c["Id"][:12],
                    "name": c["Name"].lstrip('/'),
                    "status": c["State"]["Status"],
                    "ports": c.get("NetworkSettings", {}).get("Ports", {}),
                }
                for c in assignment_containers
            ]
        except Exception as e:
            status["errors"].append(f"Container query error: {str(e)}")

        status["status"] = "healthy" if not status["errors"] else "degraded"
        return status

    @staticmethod
    def _age_hours(container: Dict) -> float:
        created = container.get('Created')
        created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
        return (datetime.now(timezone.utc) - created_dt).total_seconds() / 3600

    @staticmethod
    def cleanup_old_containers(hours_old: int = 24) -> Dict:
        """Clean up containers older than specified hours"""
        result = {"cleaned": 0, "failed": 0, "errors": []}

        if not ManagementService._docker_available():
            result["errors"].append("Docker daemon not accessible")
            return result

        try:
            containers = ManagementService._list_containers(all_containers=True, name_filter='assignment')
        except Exception as e:
            result["errors"].append(f"Cleanup error: {str(e)}")
            return result

        for container in containers:
            name = container.get('Name', '').lstrip('/')
            try:
                if ManagementService._age_hours(container) <= hours_old:
                    continue

                container_id = container['Id']
                if container.get('State', {}).get('Status') != 'exited':
                    _run(['stop', '-t', '5', container_id], check=False)

                try:
                    _run(['rm', container_id], check=True)
                    result["cleaned"] += 1
                except Exception as e:
                    result["failed"] += 1
                    result["errors"].append(f"Failed to remove {name}: {str(e)}")

            except Exception as e:
                result["failed"] += 1
                result["errors"].append(f"Error processing {name}: {str(e)}")

        return result

    @staticmethod
    def cleanup_all_containers() -> Dict:
        """Force cleanup all assignment containers"""
        result = {"removed": 0, "failed": 0, "errors": []}

        if not ManagementService._docker_available():
            result["errors"].append("Docker daemon not accessible")
            return result

        try:
            containers = ManagementService._list_containers(all_containers=True, name_filter='assignment')
        except Exception as e:
            result["errors"].append(f"Cleanup error: {str(e)}")
            return result

        for container in containers:
            name = container.get('Name', '').lstrip('/')
            container_id = container['Id']
            try:
                if container.get('State', {}).get('Status') != 'exited':
                    _run(['stop', '-t', '5', container_id], check=False)

                try:
                    _run(['rm', '-f', container_id], check=True)
                    result["removed"] += 1
                except Exception as e:
                    result["failed"] += 1
                    result["errors"].append(f"Failed to remove {name}: {str(e)}")

            except Exception as e:
                result["failed"] += 1
                result["errors"].append(f"Error: {str(e)}")

        return result

    @staticmethod
    def get_container_info(container_id: str) -> Dict:
        """Get detailed info about a container"""
        try:
            inspect_out = _run(['inspect', container_id], check=True).stdout
            container = json.loads(inspect_out)[0]

            image = container.get('Config', {}).get('Image', container['Image'][:12])

            memory_stats = {}
            try:
                stats_out = _run(
                    ['stats', '--no-stream', '--format', '{{json .}}', container_id],
                    check=True,
                ).stdout
                memory_stats = json.loads(stats_out.strip())
            except Exception as e:
                logger.warning("Could not get stats for %s: %s", container_id, e)

            return {
                "id": container["Id"][:12],
                "name": container["Name"].lstrip('/'),
                "status": container["State"]["Status"],
                "created": container.get("Created"),
                "ports": container.get("NetworkSettings", {}).get("Ports", {}),
                "image": image,
                "memory_stats": memory_stats,
            }

        except Exception as e:
            return {"error": f"Could not get container info: {str(e)}"}

    @staticmethod
    def get_logs(container_id: str, lines: int = 100) -> str:
        """Get container logs"""
        try:
            result = _run(['logs', '--tail', str(lines), container_id], check=True)
            return result.stdout + result.stderr
        except Exception as e:
            return f"Error: Could not get logs: {str(e)}"

    @staticmethod
    def health_check() -> Dict:
        """Comprehensive health check of the system"""
        health = {
            "timestamp": datetime.now().isoformat(),
            "overall": "healthy",
            "components": {}
        }

        if ManagementService._docker_available():
            health["components"]["docker"] = "healthy"
        else:
            health["components"]["docker"] = "unhealthy: Docker daemon not accessible"
            health["overall"] = "unhealthy"

        # Database health
        try:
            from app.models.database import Database
            db = Database()
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
            health["components"]["database"] = "healthy"
        except Exception as e:
            health["components"]["database"] = f"unhealthy: {str(e)}"
            health["overall"] = "unhealthy"

        # LLM API health (Gemini)
        try:
            from app.services.llm_service import LLMService
            LLMService.get_client()
            health["components"]["llm_api"] = "ready"
        except Exception as e:
            health["components"]["llm_api"] = f"error: {str(e)}"

        return health

    @staticmethod
    def restart_container(container_id: str) -> Dict:
        """Restart a specific container"""
        try:
            _run(['restart', '-t', '5', container_id], check=True)
            return {
                "success": True,
                "container_id": container_id[:12],
                "status": "restarted"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def stop_container(container_id: str) -> Dict:
        """Stop a specific container"""
        try:
            _run(['stop', '-t', '5', container_id], check=True)
            return {
                "success": True,
                "container_id": container_id[:12],
                "status": "stopped"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
