import unittest
from charm.adapters.langchain import CharmLangChainAdapter

class MockLangChainRunnable:
    """Simulates a LangChain Runnable (Chain or Agent) for testing purposes."""
    def invoke(self, inputs):
        if "input" in inputs:
            return {"output": f"Processed: {inputs['input']}"}
        return {"output": "Error: Missing input"}

class TestLangChainAdapter(unittest.TestCase):
    
    def test_translation(self):
        """Test the input/output translation logic for LangChain."""
        adapter = CharmLangChainAdapter(MockLangChainRunnable())
        
        # Action
        result = adapter.invoke({"input": "Hello LangChain"})
        
        # Assert
        self.assertEqual(result["status"], "success")
        self.assertIn("Processed: Hello LangChain", result["output"])

if __name__ == "__main__":
    unittest.main()