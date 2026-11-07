"""Check an installed package in a separate Maya process using generated cubes."""
import hashlib,json,os,sys,tempfile,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'diagnostics';OUT.mkdir(exist_ok=True)
os.environ['MAYA_APP_DIR']=tempfile.mkdtemp(prefix='RevToonCheck_')
os.environ['MAYA_SKIP_USERSETUP_PY']='1'
report=dict(status='started',checks={})
initialized=False
try:
    record=json.loads((ROOT/'installation.json').read_text(encoding='utf-8'))
    package=Path(record['install_dir']);sys.path.insert(0,str(package/'scripts'))
    import reatoon
    assert Path(reatoon.__file__).resolve().is_relative_to(package.resolve())
    report['version']=reatoon.__version__
    marker=json.loads((package/'reatoon-install.json').read_text())
    package_manifest=json.loads((ROOT/'SHA256SUMS.json').read_text())
    assert reatoon.__version__==marker['version']==record['version']==package_manifest['version']
    manifest=package_manifest['files']
    assert all(hashlib.sha256((package/name).read_bytes()).hexdigest()==manifest[name] for name in marker['files'])
    report['checks']['installed_files']=len(marker['files'])
    from reatoon import accelerator
    report['accelerator_path']=accelerator.enable()
    import numpy as np,numba,llvmlite
    assert Path(numba.__file__).resolve().is_relative_to(Path(record['accelerator_dir']).resolve())
    @numba.njit
    def compiled_sum(values):return values.sum()
    assert compiled_sum(np.array([1.,2.,3.]))==6.
    report['checks']['cpu_accelerator']=dict(numba=numba.__version__,llvmlite=llvmlite.__version__,numpy=np.__version__)
    print('Checking Maya plug-in loading...',flush=True)
    import maya.standalone
    maya.standalone.initialize(name='python');initialized=True
    from maya import cmds
    cmds.loadPlugin(str(package/'plug-ins/reaPencil.py'),quiet=True)
    cmds.loadPlugin(str(package/'plug-ins/2025/revToonImage.mll'),quiet=True)
    from reatoon import maya_scene,line_graph,viewport
    a=cmds.polyCube(name='RevToonCheckA',width=2,height=2,depth=2)[0]
    b=cmds.polyCube(name='RevToonCheckB',width=2,height=2,depth=2)[0]
    cmds.move(.7,.3,.2,b);cmds.rotate(20,35,0,b)
    for obj in (a,b):
        shape=cmds.listRelatives(obj,shapes=True,fullPath=True)[0]
        cmds.setAttr(shape+'.displaySmoothMesh',2);cmds.setAttr(shape+'.smoothLevel',1)
    line=line_graph.create_line();node=line_graph.create_line_set(line,overrides=dict(outline=True,intersections=True))
    line_graph.add_targets(node,[a,b])
    settings=maya_scene.load_settings();settings.update(enabled_smooth_mesh=True,width=160,height=120)
    maya_scene.save_settings(settings)
    cmds.select([a,b]);cmds.viewFit('persp',animate=False);cmds.select(clear=True)
    print('Checking GPU intersections and outlines...',flush=True)
    data=viewport.build_draw_data(maya_scene._dag('perspShape'))
    report['checks']['gpu']=data.report
    gpu_ok=data.report['state']=='ready'
    if gpu_ok:
        assert data.report['mesh_count']==2 and data.report['smooth_mesh_count']==2
        assert data.report['intersection_diagnostics']['segments']>0
        print('Checking paged GPU intersections and cache cleanup...',flush=True)
        from reatoon.gpu_paged import PagedGPUScene
        live=viewport._gpu_scene
        from reatoon import renderer
        passes=renderer.line_style_passes(live.scene,settings)
        paged=PagedGPUScene(live.scene['meshes'],page_triangle_target=1)
        cache=Path(paged._temp.name)
        try:
            item=passes[0]
            paged.configure_face_styles(item['face_style_ids'],len(item['styles']),item.get('selected_edges'))
            points,owners,info=paged.intersections(item['styles'],settings.get('intersection_tolerance',1e-7))
            assert info['cross_page_segments']>0 and len(paged.pages)==2
            report['checks']['gpu_paging']=dict(pages=len(paged.pages),cross_page_segments=info['cross_page_segments'])
        finally:paged.close()
        assert not cache.exists()
        report['checks']['gpu_paging']['cache_cleanup']=True
    else:print('GPU check failed; continuing the independent CPU render check.',flush=True)
    print('Checking CPU render (first compilation can take longer)...',flush=True)
    start=time.perf_counter()
    result=maya_scene.render_scene(str(OUT/'test'),camera='persp',settings=settings,auxiliary_outputs=False)
    assert Path(result['paths']['beauty']).is_file()
    from PySide6.QtGui import QImage
    im=QImage(result['paths']['beauty']).convertToFormat(QImage.Format_RGBA8888)
    pixels=np.frombuffer(im.constBits(),np.uint8,count=im.sizeInBytes()).reshape(im.height(),im.bytesPerLine())[:,:im.width()*4].reshape(im.height(),im.width(),4)
    assert np.any(pixels[:,:,3]>0),'CPU render contains no lines'
    report['checks']['cpu_render']=dict(seconds=time.perf_counter()-start,image=result['paths']['beauty'],coverage_pixels=int(np.count_nonzero(pixels[:,:,3])),depth_backend=result['stats'].get('depth_backend'),segment_backend=result['stats'].get('segment_backend'))
    from reatoon.native_cpu import library
    assert library() is not None,'Native CPU library missing or unloadable'
    report['checks']['native_cpu_library']='loaded'
    print('Checking saved Pencil nodes without the Pencil runtime...',flush=True)
    assert 'Pencil4' not in (cmds.pluginInfo(query=True,listPlugins=True) or [])
    saved=Path(os.environ['MAYA_APP_DIR'])/'saved_pencil.ma'
    saved.write_text('''//Maya ASCII 2025 scene
requires maya "2025";
createNode PencilLine -n "savedPencilLine";
    setAttr ".lsz" 0;
createNode PencilLineSet -n "savedPencilSet";
createNode PencilBrushSettings -n "savedPencilBrush";
    setAttr ".siz" 2.5;
connectAttr "savedPencilSet.msg" "savedPencilLine.ls[0]";
connectAttr "savedPencilBrush.msg" "savedPencilSet.lnd[0].brs";
''',encoding='ascii')
    cmds.file(str(saved),i=True,namespace='compatCheck',executeScriptNodes=False)
    from reatoon import pencil_compat
    restored=pencil_compat.import_scene()
    assert restored['runtime_missing'] and len(restored['created_line_sets'])==1
    assert restored['line_sets'][0]['overrides']['line_width']==2.5
    report['checks']['missing_pencil_import']=dict(status='passed',nodes=len(restored['recovered_unknown_nodes']))
    assert cmds.renderer('revtoon',query=True,rendererUIName=True)=='ReaPencil'
    assert all(hasattr(cmds,name) for name in ('reaPencilUI','reaPencilRender','reaPencilImportPencil','revToonUI','revToonRender'))
    report['checks']['product_name_and_legacy_commands']='passed'
    report['checks']['maya_plugins']=cmds.pluginInfo(query=True,listPlugins=True)
    report['status']='passed' if gpu_ok else 'failed'
except Exception:
    report['status']='failed';report['error']=traceback.format_exc();print(report['error'],flush=True)
finally:
    if initialized:
        cmds.file(new=True,force=True)
        maya.standalone.uninitialize()
    (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('CHECK',report['status'],str(OUT/'report.json'),flush=True)
sys.exit(0 if report['status']=='passed' else 1)
