import unittest
from charm.adapters.crewai import CharmCrewAIAdapter

class MockCrew:
    """Simulates a CrewAI Agent for testing purposes."""
    def kickoff(self, inputs):
        if "topic" in inputs:
            return type('Obj', (), {'raw': f"Processed: {inputs['topic']}"})
        return type('Obj', (), {'raw': "Error: Missing topic"})

class TestCrewAIAdapter(unittest.TestCase):
    
    def test_translation(self):
        """Test the input translation logic (input -> topic) for CrewAI."""
        adapter = CharmCrewAIAdapter(MockCrew())
        
        # Action
        result = adapter.invoke({"input": "Hello Crew"})
        
        # Assert
        self.assertEqual(result["status"], "success")
        self.assertIn("Processed: Hello Crew", result["output"])

if __name__ == "__main__":
    unittest.main()