from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import json
ROOT=Path(__file__).resolve().parent
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
f=ImageFont.truetype(FONT,24)
frames=[(0,0.0),(36,15.0),(48,20.0),(96,40.0),(132,55.0),(142,59.1666667)]
for name,subset in [('source_extract',frames[:3]),('load_release',frames[3:])]:
    canvas=Image.new('RGB',(1920,3*584),'white'); d=ImageDraw.Draw(canvas)
    for i,(n,t) in enumerate(subset):
        p=next((ROOT/'frames').glob(f'frame_{n:03d}_*.jpg'))
        src=Image.open(p)
        for half in range(2):
            im=src.crop((1920*half,0,1920*(half+1),1080)).resize((960,540))
            canvas.paste(im,(960*half,i*584+44))
            d.text((960*half+12,i*584+9),f'{"Wide" if half==0 else "Hand camera"} | frame {n} | encoded t={t:.3f} s',fill='black',font=f)
    canvas.save(ROOT/f'{name}_dual_view.jpg',quality=92)
# Hand counted upper grid, marker positions only, never metric geometry.
im=Image.open(ROOT/'frames/source_rack_manual_perspective_aid.png').convert('RGB')
d=ImageDraw.Draw(im); f2=ImageFont.truetype(FONT,20)
for row in range(6):
    for col in range(6):
        x=66+col*132; y=55+row*119
        d.ellipse((x-5,y-5,x+5,y+5),fill='red')
        d.text((x+8,y+5),f'{row},{col}',font=f2,fill='red',stroke_width=1,stroke_fill='white')
im.save(ROOT/'frames/source_rack_visual_count_6x6.png')
# Video local identity labels. Coordinates are in exact 3840x1080 frame.
annotations={142:[('A: target after release',(2850,760),(2980,890)),('B: pre-existing transparent item',(2290,715),(2070,775)),('Open separated fingers',(2880,315),(2650,420))]}
for n,items in annotations.items():
    src=Image.open(next((ROOT/'frames').glob(f'frame_{n:03d}_*.jpg'))).convert('RGB')
    d=ImageDraw.Draw(src)
    for label,txt,pt in items:
        d.text(txt,label,fill=(255,225,60),font=f,stroke_width=2,stroke_fill='black');d.line((txt[0],txt[1]+27,*pt),fill=(255,225,60),width=4);d.ellipse((pt[0]-9,pt[1]-9,pt[0]+9,pt[1]+9),outline=(255,225,60),width=3)
    src.save(ROOT/'frames'/f'chamber_identity_frame_{n:03d}.jpg',quality=92)
(ROOT/'visual_count_method.json').write_text(json.dumps({'count':'6 by 6 visible upper openings','basis':'Manual count of original video frame 0, aided by a manually chosen projective warp','source_visual_row_col_convention':'Only image coordinates: row increases from far/blue side to near/removed-target side; column increases left to right in rectified image. These are not CAD slot IDs.','target_image_slot_estimate':{'row':5,'column':0},'other_blue_slot_estimate':None,'blue_slot_uncertainty':'Cup height creates parallax; exact physical slot not established by this annotation.','dimensions_mm':None,'geometry_measurement':False,'previous_V0_6x8':'Not adopted. V0 specification is an implementation choice, not evidence for source rack.'},ensure_ascii=False,indent=2)+'\n')

# Wide frame 0: two different instruments are present. The foreground-left unit is the task target.
src=Image.open(next((ROOT/'frames').glob('frame_000_*.jpg'))).convert('RGB')
d=ImageDraw.Draw(src)
for label,txt,pt in [('Task instrument (foreground)',(30,650),(470,850)),('Neighbor instrument',(1010,105),(1160,430)),('Full white source rack',(1070,825),(925,820)),('Target item at source',(1090,930),(930,865))]:
    d.text(txt,label,fill=(255,225,60),font=f,stroke_width=2,stroke_fill='black');d.line((txt[0],txt[1]+27,*pt),fill=(255,225,60),width=4);d.ellipse((pt[0]-9,pt[1]-9,pt[0]+9,pt[1]+9),outline=(255,225,60),width=3)
src.crop((0,0,1920,1080)).save(ROOT/'frames/wide_scene_roles_frame_000.jpg',quality=92)
