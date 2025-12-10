import os
import unittest

# Import directly as we assume the package is installed via pip install -e .
from charm.core.loader import CharmLoader

class TestCharmLoader(unittest.TestCase):
    
    def setUp(self):
        # 1. Locate the fixtures directory
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.fixtures_dir = os.path.join(base_dir, "fixtures")

    def test_load_all_fixtures(self):
        """
        Automatically scans all sub-projects in the fixtures directory and attempts to load/execute them.
        This allows contributors to add new test cases by simply adding a folder without modifying the test code.
        """
        print(f"\nStarting Auto-Discovery Test in: {self.fixtures_dir}")
        
        if not os.path.exists(self.fixtures_dir):
             self.fail(f"Fixtures directory not found: {self.fixtures_dir}")

        # Scan all directories under fixtures (filtering out __pycache__ and .DS_Store)
        projects = [
            d for d in os.listdir(self.fixtures_dir) 
            if os.path.isdir(os.path.join(self.fixtures_dir, d)) 
            and not d.startswith("__") 
            and not d.startswith(".")
        ]

        if not projects:
            self.fail("No fixture projects found! Please add at least one mock project.")

        print(f"Found {len(projects)} projects: {projects}")

        for project_name in projects:
            with self.subTest(project=project_name):
                project_path = os.path.join(self.fixtures_dir, project_name)
                print(f"\n   Testing Project: [{project_name}]")
                print(f"      Path: {project_path}")

                try:
                    # 1. Load
                    wrapper = CharmLoader.load(project_path)
                    print(f"      Loaded Wrapper for {wrapper.config.runtime.adapter.type}")
                    
                    # 2. Invoke
                    result = wrapper.invoke({"input": "AutoTest"})
                    
                    # 3. Assert
                    # Pass as long as the status is not 'error'
                    self.assertNotEqual(result.get("status"), "error", f"Agent execution failed: {result.get('message')}")
                    
                    # Safely print the first 50 characters of the output
                    output_preview = str(result.get('output', ''))[:50]
                    print(f"      Execution Success: {output_preview}...")
                    
                except Exception as e:
                    self.fail(f"Project '{project_name}' failed: {e}")

if __name__ == "__main__":
    unittest.main()