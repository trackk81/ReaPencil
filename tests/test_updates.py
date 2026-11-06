import hashlib,importlib.util,json,os,stat,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from reatoon import update_core as core

class UpdateTests(unittest.TestCase):
    def release(self,v='0.8.5'):
        name='ReaPencil-'+v+'-Maya2025-Windows-x64.zip'
        return dict(tag_name='v'+v,assets=[dict(name=name,state='uploaded',size=123,digest='sha256:'+'a'*64,
                    browser_download_url='https://github.com/trackk81/ReaPencil/releases/download/v'+v+'/'+name)])

    def test_semantic_versions_and_no_downgrade(self):
        self.assertTrue(core.release_info(self.release('0.8.10'),'0.8.9')['available'])
        self.assertFalse(core.release_info(self.release(),'0.8.6')['available'])
        for s in ('1.0','1.2.3-beta','01.2.3','v1.2.3/evil'):
            with self.assertRaises(ValueError):core.version(s)

    def test_reject_unverified_or_external_release(self):
        for change in ('digest','url','prerelease','size'):
            r=self.release()
            if change=='digest':r['assets'][0]['digest']=None
            if change=='url':r['assets'][0]['browser_download_url']='https://github.com.evil.test/payload.zip'
            if change=='prerelease':r['prerelease']=True
            if change=='size':r['assets'][0]['size']=core.MAX_ARCHIVE+1
            with self.assertRaises(ValueError):core.release_info(r,'0.8.4')

    def make_zip(self,folder,entries=None,alter=None):
        files={'tools/install.py':b'# installer','plug-ins/reaPencil.py':b'# entry','scripts/reatoon/__init__.py':b'__version__="0.8.5"'}
        manifest=dict(product='ReaPencil',version='0.8.5',platform='Windows x64',maya='2025',update_protocol=1,
                      dependencies=core.DEPENDENCIES,files={n:hashlib.sha256(v).hexdigest() for n,v in files.items()})
        if alter:alter(files,manifest)
        archive=folder/'test.zip'
        with zipfile.ZipFile(archive,'w') as z:
            for n,v in files.items():z.writestr('package/'+n,v)
            z.writestr('package/SHA256SUMS.json',json.dumps(manifest))
            for n,v in entries or []:z.writestr(n,v)
        return archive

    def test_extract_and_verify(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);root=core.extract_verified(self.make_zip(p),p/'out','0.8.5')
            self.assertEqual(core.verify_payload(root,'0.8.5')['version'],'0.8.5')

    def test_path_traversal_and_case_collisions(self):
        for name in ('../escape','/absolute','package/../../escape','package/evil\\escape','package/C:escape',
                     'package/NUL.txt','package/foo.','PACKAGE/tools/install.py'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as d:
                p=Path(d)
                with self.assertRaises(ValueError):core.extract_verified(self.make_zip(p,[(name,b'bad')]),p/'out','0.8.5')
                self.assertFalse((p/'escape').exists())

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);z=self.make_zip(p)
            info=zipfile.ZipInfo('package/link');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
            with zipfile.ZipFile(z,'a') as f:f.writestr(info,'/tmp/outside')
            with self.assertRaises(ValueError):core.extract_verified(z,p/'out','0.8.5')

    def test_tampered_missing_extra_and_dependency_changes(self):
        def tamper(f,m):f['plug-ins/reaPencil.py']=b'changed'
        def missing(f,m):del f['plug-ins/reaPencil.py']
        def extra(f,m):f['extra.py']=b'extra'
        def dependency(f,m):m['dependencies']={'numba':'999'}
        for alter in (tamper,missing,extra,dependency):
            with self.subTest(alter=alter.__name__),tempfile.TemporaryDirectory() as d:
                p=Path(d)
                with self.assertRaises(ValueError):core.extract_verified(self.make_zip(p,alter=alter),p/'out','0.8.5')

    def test_download_hash_is_checked_before_extraction(self):
        import io
        class Response(io.BytesIO):
            def geturl(self):return 'https://release-assets.githubusercontent.com/file'
        with tempfile.TemporaryDirectory() as d,patch.object(core,'urlopen',return_value=Response(b'bad')):
            info=core.release_info(self.release(),'0.8.4');info['size']=3
            with self.assertRaisesRegex(ValueError,'SHA-256'):core.stage(info,Path(d))

    def test_transactional_install_rolls_back_and_reinstalls(self):
        spec=importlib.util.spec_from_file_location('checked_install',Path(__file__).resolve().parents[1]/'tools/install.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);source=p/'source';target=p/'target';modules=p/'modules'
            for name,data in {'scripts/reatoon/__init__.py':'__version__="0.8.5"','plug-ins/reaPencil.py':'new entry',
                              'scripts/added.py':'new file','rendererDesc/renderer.xml':'new xml'}.items():
                f=source/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(data)
            target.mkdir();(target/'reatoon-install.json').write_text('{"version":"0.8.4"}')
            (target/'plug-ins').mkdir();(target/'plug-ins/reaPencil.py').write_text('old entry')
            modules.mkdir();module=modules/'ReaToon.mod';module.write_text('old module')
            original=os.replace
            def fail_once(a,b):
                if Path(b)==module and '.restore.' not in str(a):raise PermissionError('simulated locked target')
                return original(a,b)
            with patch.object(mod,'ROOT',source),patch.object(mod.os,'replace',side_effect=fail_once):
                with self.assertRaises(PermissionError):mod.install(modules,target)
            self.assertEqual((target/'plug-ins/reaPencil.py').read_text(),'old entry')
            self.assertEqual(json.loads((target/'reatoon-install.json').read_text())['version'],'0.8.4')
            self.assertEqual(module.read_text(),'old module');self.assertFalse((target/'scripts/added.py').exists())
            with patch.object(mod,'ROOT',source):mod.install(modules,target)
            self.assertEqual(json.loads((target/'reatoon-install.json').read_text())['version'],'0.8.5')
            self.assertEqual((target/'plug-ins/reaPencil.py').read_text(),'new entry')

if __name__=='__main__':unittest.main()
