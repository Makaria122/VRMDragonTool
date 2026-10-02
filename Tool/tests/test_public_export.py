import importlib.util,sys,tempfile,unittest
from pathlib import Path
TOOL=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('public_export',TOOL/'export_public.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class PublicExportTests(unittest.TestCase):
    def test_allowlist_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'source';root.mkdir()
            for name in module.TOP_FILES:
                (root/name).write_text('public text',encoding='utf-8')
            (root/'Tool').mkdir()
            for name in module.TOOL_FILES:(root/'Tool'/name).write_text('public text',encoding='utf-8')
            (root/'Tool/um').mkdir();(root/'Tool/um/test.py').write_text('print(1)',encoding='utf-8')
            for name in ('PrivateData/secret.gmd','Tool/userdata/settings.json','Tool/runtime/ollama.exe','Tool/MODLOG.md'):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'private')
            out=Path(t)/'public';module.export(out,root)
            self.assertTrue((out/'public-manifest.json').is_file())
            self.assertFalse((out/'PrivateData').exists());self.assertFalse((out/'Tool/userdata').exists())
            self.assertFalse((out/'Tool/runtime').exists());self.assertFalse((out/'Tool/MODLOG.md').exists())
            with self.assertRaises(ValueError):module.export(out,root)
            (root/'Tool/um/test.py').write_text('C:'+chr(92)+'Users'+chr(92)+'someone'+chr(92)+'private',encoding='utf-8')
            with self.assertRaises(ValueError):module.export(Path(t)/'public2',root)

if __name__=='__main__':unittest.main()
