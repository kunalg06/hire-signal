"""System management service for Docker and application lifecycle"""

import docker
import logging
import subprocess
import os
from typing import Dict, List, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

class ManagementService:
    """Manage application lifecycle, Docker services, and system health"""

    @staticmethod
    def get_docker_client():
        """Get Docker client"""
        try:
            docker_host = os.getenv('DOCKER_HOST')
            if docker_host:
                return docker.DockerClient(base_url=docker_host)
            return docker.from_env()
        except Exception as e:
            logger.error("Could not connect to Docker: %s", e)
            return None

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

        try:
            client = ManagementService.get_docker_client()
            if not client:
                status["status"] = "error"
                status["errors"].append("Docker daemon not accessible")
                return status

            # Check Docker daemon
            try:
                client.ping()
                status["services"]["docker"] = "running"
            except Exception as e:
                status["services"]["docker"] = "not_responding"
                status["errors"].append(f"Docker daemon error: {str(e)}")

            # Get running containers related to this app
            try:
                containers = client.containers.list()
                assignment_containers = [c for c in containers if 'assignment' in c.name]

                status["containers"]["total_running"] = len(containers)
                status["containers"]["assignment_containers"] = len(assignment_containers)
                status["containers"]["containers"] = [
                    {
                        "id": c.id[:12],
                        "name": c.name,
                        "status": c.status,
                        "ports": c.ports
                    }
                    for c in assignment_containers
                ]
            except Exception as e:
                status["errors"].append(f"Container query error: {str(e)}")

            # Determine overall status
            if not status["errors"]:
                status["status"] = "healthy"
            else:
                status["status"] = "degraded"

        except Exception as e:
            status["status"] = "error"
            status["errors"].append(str(e))

        return status

    @staticmethod
    def cleanup_old_containers(hours_old: int = 24) -> Dict:
        """Clean up containers older than specified hours"""
        result = {
            "cleaned": 0,
            "failed": 0,
            "errors": []
        }

        try:
            client = ManagementService.get_docker_client()
            if not client:
                result["errors"].append("Docker daemon not accessible")
                return result

            containers = client.containers.list(all=True)

            for container in containers:
                if 'assignment' not in container.name:
                    continue

                try:
                    # Check if container is old enough
                    created = container.attrs.get('Created')
                    if created:
                        from datetime import datetime, timezone, timedelta
                        created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                        age_hours = (datetime.now(timezone.utc) - created_dt).total_seconds() / 3600

                        if age_hours > hours_old:
                            if container.status != 'exited':
                                try:
                                    container.stop(timeout=5)
                                except:
                                    pass

                            try:
                                container.remove()
                                result["cleaned"] += 1
                            except Exception as e:
                                result["failed"] += 1
                                result["errors"].append(f"Failed to remove {container.name}: {str(e)}")

                except Exception as e:
                    result["failed"] += 1
                    result["errors"].append(f"Error processing {container.name}: {str(e)}")

        except Exception as e:
            result["errors"].append(f"Cleanup error: {str(e)}")

        return result

    @staticmethod
    def cleanup_all_containers() -> Dict:
        """Force cleanup all assignment containers"""
        result = {
            "removed": 0,
            "failed": 0,
            "errors": []
        }

        try:
            client = ManagementService.get_docker_client()
            if not client:
                result["errors"].append("Docker daemon not accessible")
                return result

            containers = client.containers.list(all=True)

            for container in containers:
                if 'assignment' not in container.name:
                    continue

                try:
                    if container.status != 'exited':
                        try:
                            container.stop(timeout=5)
                        except:
                            pass

                    try:
                        container.remove(force=True)
                        result["removed"] += 1
                    except Exception as e:
                        result["failed"] += 1
                        result["errors"].append(f"Failed to remove {container.name}: {str(e)}")

                except Exception as e:
                    result["failed"] += 1
                    result["errors"].append(f"Error: {str(e)}")

        except Exception as e:
            result["errors"].append(f"Cleanup error: {str(e)}")

        return result

    @staticmethod
    def get_container_info(container_id: str) -> Dict:
        """Get detailed info about a container"""
        try:
            client = ManagementService.get_docker_client()
            if not client:
                return {"error": "Docker daemon not accessible"}

            container = client.containers.get(container_id)

            return {
                "id": container.id[:12],
                "name": container.name,
                "status": container.status,
                "created": container.attrs.get('Created'),
                "ports": container.ports,
                "image": container.image.tags[0] if container.image.tags else container.image.id[:12],
                "memory_stats": container.stats(stream=False).get('memory_stats', {})
            }

        except Exception as e:
            return {"error": f"Could not get container info: {str(e)}"}

    @staticmethod
    def get_logs(container_id: str, lines: int = 100) -> str:
        """Get container logs"""
        try:
            client = ManagementService.get_docker_client()
            if not client:
                return "Error: Docker daemon not accessible"

            container = client.containers.get(container_id)
            logs = container.logs(tail=lines, stdout=True, stderr=True)

            if isinstance(logs, bytes):
                return logs.decode('utf-8')
            return str(logs)

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

        # Docker health
        try:
            client = ManagementService.get_docker_client()
            client.ping()
            health["components"]["docker"] = "healthy"
        except Exception as e:
            health["components"]["docker"] = f"unhealthy: {str(e)}"
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

        # LLM API health (OpenRouter)
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
            client = ManagementService.get_docker_client()
            if not client:
                return {"error": "Docker daemon not accessible"}

            container = client.containers.get(container_id)
            container.restart(timeout=5)

            return {
                "success": True,
                "container_id": container_id[:12],
                "status": "restarted"
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def stop_container(container_id: str) -> Dict:
        """Stop a specific container"""
        try:
            client = ManagementService.get_docker_client()
            if not client:
                return {"error": "Docker daemon not accessible"}

            container = client.containers.get(container_id)
            container.stop(timeout=5)

            return {
                "success": True,
                "container_id": container_id[:12],
                "status": "stopped"
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
