
import unittest
import os
import sys
from manufacturing_pipeline.core.config import SystemConfig
from manufacturing_pipeline.core.utils import get_output_dir, PROJECT_ROOT

class TestConfig(unittest.TestCase):
    def test_system_config_defaults(self):
        config = SystemConfig()
        # Should contain FreeCAD.app (assuming default)
        self.assertIn("FreeCAD.app", config.freecad_path)
        
    def test_system_config_paths(self):
        config = SystemConfig()
        if sys.platform == 'darwin':
            self.assertTrue(config.freecad_python.endswith("bin/python"))
            self.assertTrue(config.freecad_lib.endswith("Resources/lib"))

class TestUtils(unittest.TestCase):
    def test_project_root(self):
        # PROJECT_ROOT should point to the alestest directory
        # We assume tests running from root
        expected_suffix = "alestest" # or just check if it exists
        self.assertTrue(os.path.isdir(PROJECT_ROOT))
        self.assertTrue(os.path.exists(os.path.join(PROJECT_ROOT, "manufacturing_pipeline")))

    def test_get_output_dir(self):
        dummy_file = "/tmp/testfile.stp"
        out_dir, part_name = get_output_dir(dummy_file)
        
        self.assertEqual(part_name, "testfile")
        self.assertTrue(out_dir.endswith("testfile"))
        
        # Cleanup
        if os.path.exists(out_dir):
            os.rmdir(os.path.join(out_dir, "images"))
            os.rmdir(out_dir)

if __name__ == '__main__':
    unittest.main()
