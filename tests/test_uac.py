import unittest
from pydantic import ValidationError
from charm.contracts.uac import CharmConfig

class TestContracts(unittest.TestCase):
    
    def setUp(self):
        # Prepare a standard valid configuration for testing
        self.valid_data = {
            "version": "0.4.1",
            "persona": {"name": "UI Tester", "description": "Test"},
            "interface": {
                "input": {"topic": {"type": "string", "x-ui-widget": "textarea"}},
                "output": {}
            },
            "runtime": {
                "adapter": {"type": "crewai", "entry_point": "main:app"}
            }
        }

    def test_happy_path(self):
        """Test that a valid configuration parses correctly and includes UI Hints."""
        cfg = CharmConfig(**self.valid_data)
        self.assertEqual(cfg.persona.name, "UI Tester")
        self.assertEqual(cfg.runtime.adapter.type, "crewai")
        
        # Verify arbitrary field extension (UI Hint)
        widget = cfg.interface.input["topic"].get("x-ui-widget")
        self.assertEqual(widget, "textarea")

    def test_missing_field(self):
        """Test validation error when a required field is missing."""
        invalid_data = self.valid_data.copy()
        # Intentionally remove 'adapter' to trigger validation error
        del invalid_data["runtime"]["adapter"]
        
        # Expect ValidationError to be raised
        with self.assertRaises(ValidationError):
            CharmConfig(**invalid_data)

    def test_invalid_type(self):
        """Test validation error on invalid data types (e.g., string instead of number)."""
        invalid_data = self.valid_data.copy()
        # Intentionally provide a string where a number is expected
        invalid_data["pricing"] = {"type": "free", "amount": "not-a-number"}
        
        with self.assertRaises(ValidationError):
            CharmConfig(**invalid_data)

if __name__ == "__main__":
    unittest.main()