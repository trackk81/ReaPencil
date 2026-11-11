from pathlib import Path
import json,sys,importlib.util,time
import numpy as np
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'scripts'))
from reatoon import renderer as r,stroke_presets as oracle,preview_brush_batch as batch
rng=np.random.default_rng(203);cases=[]
for ortho in (False,True):
 camera=r._camera(dict(position=[0,0,10],target=[0,0,0],projection='orthographic' if ortho else 'perspective',ortho_width=12),640,480)
 points=rng.uniform([-12,-8,-2],[12,8,10.1],(80,2,3));points[0]=0.;points[1]=[[0,0,10],[0,0,0]]
 phase=batch.domains(points,camera);phase[::3]=phase[::3,::-1]
 for period in (2.,16.,20.,51.7):
  style=dict(r.DEFAULTS,line_pattern=1,brush_preset=0,pattern_period=period,line_width=3.2)
  pairs=[];uv=[];sources=[];bits=[]
  for i,p in enumerate(points):
   for a,t,thin in oracle.expand(p,style,camera,phase=phase[i]):
    pairs.append(a);uv.append(t);sources.append(np.full(len(a),i));bits.append(np.full(len(a),thin))
  a,t,source,thin=batch.expand(points,style,camera,phase)
  np.testing.assert_array_equal(np.concatenate(sources),source)
  np.testing.assert_array_equal(np.concatenate(bits),thin)
  np.testing.assert_allclose(np.concatenate(uv),t,atol=1e-11,rtol=1e-11)
  np.testing.assert_allclose(np.concatenate(pairs),a,atol=1e-9,rtol=1e-10)
  cases.append(dict(ortho=ortho,period=period,segments=len(a)))
print('Clean Dash matches scalar reference:',len(cases),'cases')
