"""Original, reproducible tileable coverage examples; no external artwork."""
from pathlib import Path
import math, json, hashlib, zipfile, shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont
R=Path(__file__).resolve().parents[1];D=R/'validation/png_examples198';D.mkdir(parents=True,exist_ok=True)
OUT=R/'examples/PNGPatterns';OUT.mkdir(parents=True,exist_ok=True)
items=[];S=4;W,H=256,64
def save(name,kind,a,label,period,height):
    folder=OUT/('Line_Patterns' if kind=='line' else 'Brush_Strokes');folder.mkdir(exist_ok=True)
    image=Image.new('RGBA',(W,H),(0,0,0,0));image.putalpha(a)
    path=folder/(name+'.png');image.save(path)
    items.append(dict(file=path.relative_to(OUT).as_posix(),kind=kind,label=label,width=W,height=H,repeat_px=period,height_or_brush_width_px=height,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
def motif(name,label,draw,period=64,height=16):
    a=Image.new('L',(W*S,H*S));d=ImageDraw.Draw(a)
    def line(points,width=3):d.line([(int(x*S),int(y*S)) for x,y in points],fill=255,width=int(width*S),joint='curve')
    draw(d,line);save(name,'line',a.resize((W,H),Image.Resampling.LANCZOS),label,period,height)
motif('01_arrow','화살표',lambda d,l:(l([(0,32),(200,32)],5),d.polygon([(180*S,8*S),(246*S,32*S),(180*S,56*S)],fill=255)),72,18)
motif('02_wave','물결',lambda d,l:l([(x,32+20*math.sin(2*math.pi*x/W)) for x in np.linspace(0,W,600)],3),64,16)
motif('03_zigzag','지그재그',lambda d,l:l([(0,32),(64,10),(128,32),(192,54),(256,32)],3),48,12)
motif('04_stitches','바느질',lambda d,l:[l([(x-14,13),(x+14,51)],3) for x in (-32,32,96,160,224,288)],64,16)
motif('05_loops','고리',lambda d,l:l([(128+128*t+24*math.sin(2*math.pi*t),32+22*math.cos(2*math.pi*t)) for t in np.linspace(-1,1,900)],3),64,16)
motif('06_dot_dash','점과 긴 대시',lambda d,l:(l([(20,32),(150,32)],5),d.ellipse((195*S,27*S,205*S,37*S),fill=255)),64,16)
x=np.arange(W)[None,:]/W;y=np.arange(H)[:,None];rng=np.random.default_rng(198)
grain=rng.random((H,W));center=31.5+2*np.sin(2*np.pi*x)+np.sin(6*np.pi*x)
def strip(radius,soft=1):return np.clip((radius-np.abs(y-center))/soft,0,1)
textures=[
('01_ink','잉크',strip(22+1.5*np.sin(10*np.pi*x),2)*(0.93+0.07*grain)),
('02_dry_brush','마른 붓',strip(23,3)*np.clip((grain-.23)*2.2,0,1)*(0.55+0.45*np.sin(y*1.3)**2)),
('03_charcoal','목탄',strip(23,7)*np.clip((grain-.12)*1.6,0,1)),
('04_soft','부드러운 붓',np.exp(-((y-center)/14)**2)*(0.96+0.04*np.cos(2*np.pi*x))),
('05_bristles','붓결',strip(25,3)*(0.12+0.88*np.sin(y*0.72+0.2*np.sin(2*np.pi*x))**8)),
('06_worn_ink','닳은 잉크',strip(23,2)*(grain>.12)*(0.78+0.22*np.cos(6*np.pi*x))) ]
for name,label,a in textures:
    # Match edge coverage for seamless horizontal repetition.
    a=np.broadcast_to(a,(H,W)).copy();a[:,-1]=a[:,0]
    save(name,'brush',Image.fromarray(np.uint8(np.clip(a,0,1)*255)),label,64,16)
manifest=dict(version='0.8.73',license='CC0-1.0',original_artwork=True,seed=198,examples=items)
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
readme='''# ReaPencil PNG 예제 / PNG examples

ReaPencil **0.8.73 이상**이 필요합니다. 아래 PNG는 직접 만든 예제이며 CC0로 자유롭게 수정·사용할 수 있습니다.

1. 라인 창에서 라인셋 선택 → 속성 편집기의 **선 형태 / 브러시 프리셋**을 엽니다.
2. 라인 패턴: **선 형태 → 라인 PNG 불러오기**에서 `Line_Patterns`의 PNG 선택.
3. 붓 질감: **브러시 스트로크 → 브러시 PNG 불러오기**에서 `Brush_Strokes`의 PNG 선택.
4. 이미지 채널은 **자동** 또는 **Alpha**. 투명 배경의 검정 마스크이며 색은 라인셋 색상을 따릅니다.
5. 일반 프리뷰 또는 CPU 렌더로 확인합니다. 고속 프리뷰는 이 효과를 완전히 표시하지 않습니다.

라인 PNG의 권장 시작값: 패턴 간격 64px, 패턴 높이 16px. 화살표는 72/18, 지그재그는 48/12.
브러시 PNG의 권장 시작값: 라인셋 선폭 16px, 브러시 폭 배율 1, PNG 반복 길이 64px, 잉크 밀도 1.
선폭 4px에서는 반복 길이도 16px로 줄이면 원본 비율에 가깝습니다. 얇은 선에서는 질감 차이가 작습니다.
라인과 브러시 PNG를 동시에 적용하면 두 마스크가 곱해집니다. 먼저 한쪽만 적용해 비교하세요.
마음에 드는 설정은 **새 프리셋 추가**로 저장하세요. 불러온 이미지 데이터는 장면과 프리셋에 포함됩니다.

`CONTACT_SHEET.png`는 비교용 전체 미리보기이므로 패턴으로 불러오지 마세요.
PNG는 256×64px이며 지원 한도는 변환 후 최대 512px입니다. 일반 프리뷰와 CPU는 안티앨리어싱이 달라 완전히 같은 픽셀 결과는 아닙니다.

English: import individual transparent PNG files using the Line PNG / Brush PNG buttons in the preset editor. Use Auto/Alpha; Line Set determines color. General Preview and CPU rendering support these masks; Fast Preview does not fully reproduce them. Suggested repeat/height: line 64/16px, brush repeat 64px with Line Set width 16px. Save to a user preset after adjusting. Artwork is CC0.
'''
(OUT/'README_KO.md').write_text(readme,encoding='utf8')
(OUT/'LICENSE.txt').write_text('CC0 1.0 Universal\nOriginal ReaPencil PNG example artwork, dedicated to the public domain.\nhttps://creativecommons.org/publicdomain/zero/1.0/\n',encoding='utf8')
sheet=Image.new('RGB',(1000,80+len(items)*76),'white');draw=ImageDraw.Draw(sheet)
font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',17)
draw.text((24,18),'ReaPencil 0.8.73 — PNG 라인 패턴 / 브러시 스트로크',font=font,fill='black')
for i,it in enumerate(items):
    yy=70+i*76;draw.text((20,yy+10),it['kind']+' / '+it['label'],font=font,fill='black')
    tile=Image.open(OUT/it['file']);tile=tile.resize((256,64))
    for j in range(3):sheet.paste(tile,(220+j*256,yy),tile)
sheet.save(OUT/'CONTACT_SHEET.png')
pack=R/'dist/ReaPencil-0.8.73-PNG-Examples.zip'
with zipfile.ZipFile(pack,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(OUT.rglob('*')):
        if p.is_file():z.write(p,'ReaPencil-PNG-Examples/'+p.relative_to(OUT).as_posix())
pack.with_suffix('.sha256').write_text(hashlib.sha256(pack.read_bytes()).hexdigest()+'  '+pack.name+'\n',encoding='ascii')
target=Path.home()/'Downloads/ReaPencil-0.8.73-PNG-Examples';assert not target.exists();shutil.copytree(OUT,target)
(D/'assets.json').write_text(json.dumps(dict(passed=True,count=len(items),folder=str(target),archive=str(pack),sha256=hashlib.sha256(pack.read_bytes()).hexdigest()),indent=2),encoding='utf8')
print(json.dumps(dict(count=len(items),folder=str(target),archive=str(pack))))
