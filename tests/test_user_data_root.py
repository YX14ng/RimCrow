import os
import unittest

from backend.profile.user_data_root import UserDataRoot
from tests.host_paths import host_path


class TestUserDataRoot(unittest.TestCase):
    def test_from_raw_fixes_default_config_child_to_root(self):
        default_root = os.path.normpath(host_path("C:/Users/Test/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios"))

        result = UserDataRoot.from_raw(
            default_root + "/Config",
            default_roots=[default_root],
        )

        self.assertEqual(result.root_path, default_root)
        self.assertTrue(result.was_corrected)
        self.assertEqual(result.config_dir, os.path.join(default_root, "Config"))
        self.assertEqual(result.mods_config_file, os.path.join(default_root, "Config", "ModsConfig.xml"))

    def test_from_raw_fixes_default_modsconfig_file_to_root(self):
        default_root = os.path.normpath(host_path("C:/Users/Test/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios"))

        result = UserDataRoot.from_raw(
            default_root + "/Config/ModsConfig.xml",
            default_roots=[default_root],
        )

        self.assertEqual(result.root_path, default_root)
        self.assertTrue(result.was_corrected)

    def test_from_raw_rejects_non_default_child_path_guess(self):
        with self.assertRaises(ValueError):
            UserDataRoot.from_raw(
                host_path("D:/Profiles/CustomProfile/Config"),
                default_roots=[host_path("C:/Users/Test/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios")],
            )
