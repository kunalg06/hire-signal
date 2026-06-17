import docker
import os
from app.config import Config

class DockerService:
    """Docker container management service"""

    _client = None

    @classmethod
    def get_client(cls):
        """Get or initialize Docker client lazily"""
        if cls._client is None:
            try:
                docker_host = Config.DOCKER_HOST or os.getenv('DOCKER_HOST')
                if docker_host:
                    cls._client = docker.DockerClient(base_url=docker_host)
                else:
                    cls._client = docker.from_env()
            except Exception as e:
                print(f"Warning: Could not connect to Docker daemon: {e}")
                return None
        return cls._client

    @staticmethod
    def create_container(assignment_id, port):
        """Create a Docker container for an assignment"""
        client = DockerService.get_client()
        if not client:
            return None, None

        try:
            volumes = {
                'assignments_volume': {
                    'bind': '/workspace',
                    'mode': 'rw'
                }
            }

            container = client.containers.create(
                Config.DOCKER_IMAGE,
                name=f"assignment_{assignment_id}_{os.urandom(4).hex()}",
                ports={'8080/tcp': port},
                volumes=volumes,
                environment={},
                detach=True
            )

            container.start()
            return container.id, port

        except Exception as e:
            print(f"Error creating container: {e}")
            return None, None

    @staticmethod
    def get_file_from_container(container_id, file_path):
        """Extract file from Docker container"""
        import io
        import tarfile

        client = DockerService.get_client()
        if not client or not container_id:
            return None

        try:
            container = client.containers.get(container_id)
            bits, stat = container.get_archive(file_path)
            tar_stream = b''.join(bits)
            tar_file = tarfile.open(fileobj=io.BytesIO(tar_stream))

            for member in tar_file.getmembers():
                if member.isfile():
                    return tar_file.extractfile(member).read().decode('utf-8', errors='ignore')
            return None

        except Exception as e:
            print(f"  Could not read {file_path}: {str(e)[:60]}")
            return None

    @staticmethod
    def cleanup_container(container_id):
        """Stop and remove a Docker container"""
        client = DockerService.get_client()
        if not client or not container_id:
            return

        try:
            container = client.containers.get(container_id)
            container.stop(timeout=5)
            print(f"Stopped container {container_id[:12]}")
        except Exception as e:
            print(f"Error cleaning up container {container_id}: {e}")
