"""
Claude Assignment Platform - Python Client

A simple client library for interacting with the assignment platform API.

Usage:
    from client import AssignmentClient
    
    client = AssignmentClient("http://localhost:8000")
    
    # Create assignment
    assignment = client.create_assignment(
        title="Fibonacci Sequence",
        description="Implement fibonacci",
        evaluation_criteria="..."
    )
    
    # Generate link for student
    link = client.generate_link(assignment['id'])
    print(f"Student link: {link['access_url']}")
"""

import requests
import json
from typing import Optional, Dict, Any
from datetime import datetime


class AssignmentClient:
    """Client for Claude Assignment Platform API"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        Initialize the client.
        
        Args:
            base_url: The base URL of the API (default: http://localhost:8000)
        """
        self.base_url = base_url.rstrip('/')
        self.api_url = f"{self.base_url}/api"
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        Make an HTTP request to the API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without /api prefix)
            **kwargs: Additional arguments for requests
        
        Returns:
            Response JSON
        
        Raises:
            requests.exceptions.RequestException: If request fails
        """
        url = f"{self.api_url}/{endpoint}"
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()
    
    # ==================== Assignment Management ====================
    
    def create_assignment(
        self,
        title: str,
        description: str,
        evaluation_criteria: str,
        starter_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new assignment.
        
        Args:
            title: Assignment title
            description: Assignment description
            evaluation_criteria: Criteria for evaluating submissions
            starter_code: Optional starter code template
        
        Returns:
            Assignment object with id
        
        Example:
            assignment = client.create_assignment(
                title="Fibonacci",
                description="Implement fibonacci function",
                evaluation_criteria="- Must handle base cases\\n- Should be efficient",
                starter_code="def fibonacci(n):\\n    pass"
            )
            print(assignment['id'])
        """
        data = {
            "title": title,
            "description": description,
            "evaluation_criteria": evaluation_criteria,
        }
        if starter_code:
            data["starter_code"] = starter_code
        
        return self._request("POST", "assignments", json=data)
    
    def get_assignment(self, assignment_id: str) -> Dict[str, Any]:
        """
        Get assignment details.
        
        Args:
            assignment_id: The assignment ID
        
        Returns:
            Assignment object
        """
        return self._request("GET", f"assignments/{assignment_id}")
    
    # ==================== Link & Session Management ====================
    
    def generate_link(self, assignment_id: str) -> Dict[str, Any]:
        """
        Generate a unique access link for a student.
        
        Args:
            assignment_id: The assignment ID
        
        Returns:
            Link object with access_url and vscode_port
        
        Example:
            link = client.generate_link(assignment_id)
            print(f"Share this URL: {link['access_url']}")
            print(f"Link ID: {link['link_id']}")
        """
        return self._request("POST", f"generate-link/{assignment_id}")
    
    def get_session(self, link_id: str) -> Dict[str, Any]:
        """
        Get session information for a link.
        
        Args:
            link_id: The session link ID
        
        Returns:
            Session object with container and port info
        """
        return self._request("GET", f"session/{link_id}")
    
    # ==================== Submission & Evaluation ====================
    
    def submit_code(self, link_id: str, code: str) -> Dict[str, Any]:
        """
        Submit code for evaluation.
        
        Args:
            link_id: The session link ID
            code: The Python code to evaluate
        
        Returns:
            Evaluation result with score and feedback
        
        Example:
            result = client.submit_code(link_id, code)
            print(f"Score: {result['score']}/100")
            print(f"Feedback: {result['feedback']}")
        """
        return self._request("POST", f"submit/{link_id}", json={"code": code})
    
    def get_submission(self, submission_id: str) -> Dict[str, Any]:
        """
        Get a submission and its evaluation results.
        
        Args:
            submission_id: The submission ID
        
        Returns:
            Submission object with code, score, and feedback
        """
        return self._request("GET", f"submission/{submission_id}")
    
    # ==================== Batch Operations ====================
    
    def create_assignment_batch(
        self,
        assignments: list
    ) -> list:
        """
        Create multiple assignments at once.
        
        Args:
            assignments: List of assignment dicts with title, description, etc.
        
        Returns:
            List of created assignment objects
        """
        results = []
        for assignment in assignments:
            result = self.create_assignment(**assignment)
            results.append(result)
        return results
    
    def generate_links_batch(
        self,
        assignment_id: str,
        count: int
    ) -> list:
        """
        Generate multiple links for the same assignment.
        
        Args:
            assignment_id: The assignment ID
            count: Number of links to generate
        
        Returns:
            List of link objects
        """
        links = []
        for _ in range(count):
            link = self.generate_link(assignment_id)
            links.append(link)
        return links
    
    # ==================== Utility Methods ====================
    
    def health_check(self) -> Dict[str, Any]:
        """
        Check if the API is running.
        
        Returns:
            Health status
        
        Raises:
            requests.exceptions.ConnectionError: If API is not reachable
        """
        url = f"{self.base_url}/health"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()
    
    def get_api_info(self) -> Dict[str, Any]:
        """
        Get API information and available endpoints.
        
        Returns:
            API information
        """
        url = f"{self.base_url}/"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()


# ==================== Helper Functions ====================

def create_sample_assignment(client: AssignmentClient) -> Dict[str, Any]:
    """Create a sample assignment for testing."""
    return client.create_assignment(
        title="Fibonacci Sequence",
        description="Write a function that returns the nth number in the Fibonacci sequence.",
        starter_code="def fibonacci(n):\n    \"\"\"Return the nth Fibonacci number.\"\"\"\n    pass",
        evaluation_criteria=(
            "- Must handle base cases (n=0, n=1)\n"
            "- Should return correct results for n up to 10\n"
            "- Code should include a docstring\n"
            "- Should be reasonably efficient"
        )
    )


def demo_workflow(base_url: str = "http://localhost:8000"):
    """Run a complete demo workflow."""
    print("🚀 Claude Assignment Platform - Demo Workflow")
    print("=" * 50)
    
    # Initialize client
    print("\n1️⃣  Initializing client...")
    client = AssignmentClient(base_url)
    
    # Health check
    print("2️⃣  Checking API health...")
    health = client.health_check()
    print(f"   ✓ API Status: {health['status']}")
    
    # Create assignment
    print("\n3️⃣  Creating assignment...")
    assignment = create_sample_assignment(client)
    print(f"   ✓ Assignment ID: {assignment['id']}")
    print(f"   ✓ Title: {assignment['title']}")
    
    # Generate link
    print("\n4️⃣  Generating student access link...")
    link = client.generate_link(assignment['id'])
    print(f"   ✓ Link ID: {link['link_id']}")
    print(f"   ✓ VS Code URL: {link['access_url']}")
    print(f"   ✓ Port: {link['vscode_port']}")
    
    # Get session info
    print("\n5️⃣  Getting session info...")
    session = client.get_session(link['link_id'])
    print(f"   ✓ Container: {session['container_id'][:12]}...")
    print(f"   ✓ Assignment: {session['assignment_id']}")
    
    # Simulate code submission
    print("\n6️⃣  Submitting sample code...")
    sample_code = """def fibonacci(n):
    \"\"\"Return the nth Fibonacci number.\"\"\"
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)
"""
    print("   Code:")
    for line in sample_code.split('\n'):
        print(f"   {line}")
    
    # Note: Actual submission would require valid link and code
    print("\n7️⃣  Would submit for evaluation (requires valid session)")
    print("   In production: client.submit_code(link['link_id'], sample_code)")
    
    # Generate batch links
    print("\n8️⃣  Generating batch of 3 links for distribution...")
    links = client.generate_links_batch(assignment['id'], 3)
    print(f"   ✓ Created {len(links)} links:")
    for i, l in enumerate(links, 1):
        print(f"      Link {i}: {l['access_url']}")
    
    print("\n" + "=" * 50)
    print("✅ Demo complete!")
    print("\n📚 Share these links with students to start assignments.")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        demo_workflow()
    else:
        print("Python Client for Claude Assignment Platform")
        print("\nUsage:")
        print("  from client import AssignmentClient")
        print("  client = AssignmentClient()")
        print("  assignment = client.create_assignment(...)")
        print("  link = client.generate_link(assignment['id'])")
        print("\nFor a demo:")
        print("  python client.py --demo")
