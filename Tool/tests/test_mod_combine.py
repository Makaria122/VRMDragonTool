import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL))
from um.dragon_mod_package import ModPackageError, combine_mod_folders


class CombineModTests(unittest.TestCase):
    def make_mod(self, root: Path, name: str, files: dict[str, bytes]) -> Path:
        mod = root / name
        mod.mkdir()
        (mod / "mod-meta.yaml").write_text(f'Name: "{name}"\n', encoding="utf-8")
        for relative, content in files.items():
            path = mod / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return mod

    def test_combines_disjoint_payloads_and_deduplicates_identical_collision(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shared = b"same-dummy-texture"
            yagami = self.make_mod(root, "yagami", {
                "chara/tops/c_cl_x_yagami/model.gmd": b"yagami-gmd",
                "chara/dds_hires/00/v11_dummy_multi.dds": shared,
            })
            kaito = self.make_mod(root, "kaito", {
                "chara/tops/c_am_kaito/model.gmd": b"kaito-gmd",
                "chara/dds_hires/00/v11_dummy_multi.dds": shared,
            })
            out = root / "combined-output"
            result = combine_mod_folders([yagami, kaito], out, "Yagami plus Kaito")
            mod = Path(result["mod_folder"])
            self.assertEqual(result["status"], "MODS_COMBINED_UNVERIFIED")
            self.assertFalse(result["game_install_changed"])
            self.assertEqual((mod / "chara/tops/c_cl_x_yagami/model.gmd").read_bytes(), b"yagami-gmd")
            self.assertEqual((mod / "chara/tops/c_am_kaito/model.gmd").read_bytes(), b"kaito-gmd")
            self.assertEqual((mod / "chara/dds_hires/00/v11_dummy_multi.dds").read_bytes(), shared)
            self.assertEqual((out / "combine-status.json").is_file(), True)
            self.assertEqual((yagami / "chara/tops/c_cl_x_yagami/model.gmd").read_bytes(), b"yagami-gmd")

    def test_different_content_collision_refuses_before_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = self.make_mod(root, "first", {"chara/dds_hires/00/shared.dds": b"A"})
            second = self.make_mod(root, "second", {"chara/dds_hires/00/shared.dds": b"B"})
            out = root / "must-not-exist"
            with self.assertRaisesRegex(ModPackageError, "collide"):
                combine_mod_folders([first, second], out, "Conflict")
            self.assertFalse(out.exists())
            self.assertEqual((first / "chara/dds_hires/00/shared.dds").read_bytes(), b"A")
            self.assertEqual((second / "chara/dds_hires/00/shared.dds").read_bytes(), b"B")

    def test_case_insensitive_windows_path_collision_is_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = self.make_mod(root, "first", {"chara/tops/model.gmd": b"A"})
            second = self.make_mod(root, "second", {"CHARA/TOPS/MODEL.GMD": b"B"})
            with self.assertRaisesRegex(ModPackageError, "collide"):
                combine_mod_folders([first, second], root / "result", "Conflict")


if __name__ == "__main__":
    unittest.main()
