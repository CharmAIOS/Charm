import unittest
from charm.core.wrapper import CharmWrapper
from charm.adapters.base import BaseAdapter

# Simulate a failing Adapter for testing purposes
class CrashingAdapter(BaseAdapter):
    def invoke(self, inputs):
        raise ValueError("Boom! Internal Agent Error!")
    
    def get_state(self): 
        return {}
    
    def set_tools(self, tools): 
        pass

class TestWrapper(unittest.TestCase):

    def test_resilience(self):
        """Test if the Wrapper can intercept internal errors without crashing the main process."""
        wrapper = CharmWrapper(adapter=CrashingAdapter(None))
        
        # Execution: This line must not crash the program
        result = wrapper.invoke({"input": "test"})
        
        # Assert: Verify the response structure
        self.assertEqual(result.get("status"), "error")
        # Check for specific error type (CharmExecutionError or ValueError depending on implementation)
        self.assertEqual(result.get("error_type"), "CharmExecutionError") 
        self.assertIn("Boom!", result.get("message"))

if __name__ == "__main__":
    unittest.main()