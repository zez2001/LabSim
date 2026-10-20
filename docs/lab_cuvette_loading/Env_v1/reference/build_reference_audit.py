"""CPU-only reference extraction/proposal. Does not edit source media or task config."""
from pathlib import Path
import hashlib,json,subprocess
import numpy as np
from PIL import Image,ImageDraw,ImageFont
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon,Circle

ROOT=Path(__file__).resolve().parent
SOURCE=Path('/home/wujing/Desktop/来自远程/20261013')
VIDEO=SOURCE/'5afd3b2ffa3632d9c4599d8051018895_raw.mp4'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
frames=[(0,'Initial'),(36,'Grasp'),(48,'Transport'),(96,'Insertion'),(132,'Open'),(142,'Retreat')]
metadata=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(VIDEO)]))
records=[]
for i,(n,label) in enumerate(frames,1):
 path=ROOT/'frames'/f'key_{i:02}.jpg'
 if not path.exists():
  subprocess.run(['ffmpeg','-v','error','-i',str(VIDEO),'-vf',f'select=eq(n\\,{n}),scale=1920:540','-frames:v','1',str(path)],check=True)
 records.append(dict(path=str(path.relative_to(ROOT)),frame_index=n,encoded_time_s=n/2.4,role=label,
                     transform='3840x1080 decoded source resized uniformly0.5 to1920x540; JPEG encoding',sha256=sha(path)))
photos=[]
for p in sorted(SOURCE.glob('*.jpg')):
 with Image.open(p) as im: shape=list(im.size)
 photos.append(dict(file=str(p),sha256=sha(p),resolution_wh=shape))
landmarks=[dict(role='target_seat_approx',pixel_original=[470,850],confidence='rough manually selected view landmark,not center measurement'),
 dict(role='source_rack_center_approx',pixel_original=[940,820],confidence='rough top-grid center'),
 dict(role='target_lid_hinge_region',pixel_original=[380,610],confidence='hinge region; partly occluded'),
 dict(role='robot_base_partial',pixel_original=[1550,1020],confidence='only partial base visible at image bottom-right')]
im=Image.open(ROOT/'frames/key_01.jpg').crop((0,0,960,540)).convert('RGB');d=ImageDraw.Draw(im)
f=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',16)
texts=[('Target instrument/A',(12,420)),('Full6x6 rack',(590,390)),('Lid/hinge',(10,270)),('Robotproxy base',(600,495))]
for item,(label,txt) in zip(landmarks,texts):
 p=np.asarray(item['pixel_original'])/2
 d.line((*txt,p[0],p[1]),fill='#fff047',width=2);d.ellipse((p[0]-4,p[1]-4,p[0]+4,p[1]+4),outline='#fff047',width=2)
 d.text(txt,label,font=f,fill='#fff047',stroke_width=1,stroke_fill='black')
im.save(ROOT/'reference_layout_annotations.jpg',quality=92)

proposal=dict(status='CPU proposal,not final rendered/physics-verified layout',instrument_origin_m=[.36,0,.74],instrument_yaw_deg=90.,
 rack_origin_m=[-.04,-.22,.74],rack_yaw_deg=-90.,vessel_yaw_deg=90.,robot_base_m=[-.3,0,.74],
 source_A1_floor_m=[-.085,-.175,.743],blue_F6_floor_m=[.005,-.265,.743],
 side_camera=dict(eye_m=[-.5,1.,1.65],target_m=[0.,-.07,1.],upworld=[0,0,1]),
 basis='Preserve targetleft/rackright/robotright in reference side projection and visible opening; lateral offset and shorter rack-to-seat gap,not root-center autoaim',
 dimensions='Existing CAD/vessel/rack dimensions unchanged; positions/yaw video-informed engineering assumptions,not measurements')
r=np.array([[0,-1],[1,0]]);inst=np.array(proposal['instrument_origin_m'][:2]);rack=np.array(proposal['rack_origin_m'][:2]);robot=np.array(proposal['robot_base_m'][:2])
a=inst+r@np.array([-.149915535607,.147629353263]);b=inst+r@np.array([-.149915535607,.043629353263])
proposal.update(target_A_floor_m=[*a,.887],target_B_floor_m=[*b,.887],rack_to_A_center_mm=float(np.linalg.norm(a-rack)*1000),
 planar_robot_to_A_mm=float(np.linalg.norm(a-robot)*1000),
 body_front_rack_AABB_gap_mm=(inst[0]-.31268761377231436-(rack[0]+.055))*1000,
 rack_offset_in_instrument_frame_m=(r.T@(rack-inst)).tolist(),
 opening_axis_world=[-1,0,0],rack_to_instrument_not_centered=True)
fig,ax=plt.subplots(figsize=(8,6));body=np.array([[-.26025,-.317312386],[.26025,-.317312386],[.26025,.312687614],[-.26025,.312687614]])@r.T+inst
ax.add_patch(Polygon(body,fill=False,ls='--',lw=2,label='Original body XY AABB (not collision mesh)'))
ax.add_patch(Polygon(rack+np.array([[-.055,-.055],[.055,-.055],[.055,.055],[-.055,.055]]),fc='white',ec='gray',lw=2,label='110mm full6x6 rack'))
for k in range(7):
 v=-.055+k*.11/6
 ax.plot([rack[0]+v]*2,[rack[1]-.055,rack[1]+.055],color='lightgray',lw=.7)
 ax.plot([rack[0]-.055,rack[0]+.055],[rack[1]+v]*2,color='lightgray',lw=.7)
for name,p in [('A target',a),('B retained',b)]:
 ax.scatter(*p,s=55,marker='s');ax.annotate(name,p,xytext=(p[0]+.03,p[1]+.015))
for name,p,color in [('A1',proposal['source_A1_floor_m'][:2],'darkgray'),('F6 blue',proposal['blue_F6_floor_m'][:2],'blue')]:
 ax.scatter(*p,c=color,s=25);ax.annotate(name,p,xytext=(p[0]-.08,p[1]-.025),fontsize=8)
ax.add_patch(Circle(robot,.06,fc='lightblue'));ax.annotate('Franka proxy',robot,xytext=(robot[0]-.08,robot[1]+.09))
hinge=inst+r@np.array([-.10725,-.049312386]);ax.plot([hinge[0],hinge[0]],[hinge[1]-.074,hinge[1]+.074],color='black',lw=4,label='Estimated openlid hinge line')
ax.arrow(inst[0],inst[1],-.16,0,width=.002,color='green',length_includes_head=True);ax.text(inst[0]-.15,inst[1]+.015,'Opening -X',color='green')
ax.plot([rack[0],a[0]],[rack[1],a[1]],':',c='orange',label='Rack center->A (not trajectory)')
ax.set(xlabel='World X (m)',ylabel='World Y (m)',title='Env_v1 layout proposal, dimensions unchanged\nVideo-informed relation; CPU clearances are not arm/path acceptance')
ax.set_aspect('equal');ax.set_xlim(-.5,.72);ax.set_ylim(-.4,.4);ax.grid(alpha=.25);ax.legend(loc='upper left',fontsize=7)
fig.tight_layout();fig.savefig(ROOT/'layout_proposal_top.png',dpi=150);plt.close(fig)
manifest=dict(schema='labsim.Env_v1.reference_and_layout_audit.v1',source_video=str(VIDEO),source_video_sha256=sha(VIDEO),
 source_video_metadata=metadata,frame_records=records,photos=photos,
 landmarks_original_3840x1080_left_half=landmarks,
 reference_relations=['task instrument foreground-left of side view','full white6x6 rack immediatelyright/front-side of target',
 'robotbase right-side','targetA farther fromhinge thanB','source white vessel near corner and blue vessel farcorner',
 'lid remainsopen; no close/measurement/recovery task','rightview moves withhand; source controltime unknown'],
 pixel_measurements=dict(rack_minus_target_landmark_px=[470,-30],warning='Not metric or camera-calibrated; perspective andmanual selection apply'),
 reference_robot='white robot withneo marking visible; exactmodel/kinematics unverified',simulation_robot='existing Franka proxy; not realrobot digitaltwin',
 layout_proposal=proposal,Isaac_started=False,GPU_started=False,real_calibrated=False)
(ROOT/'reference_audit.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
(ROOT/'camera_defaults.json').write_text(json.dumps(__import__('demos.lab_cuvette_env_v1.cameras',fromlist=['DEFAULT_CAMERA_CONFIG']).DEFAULT_CAMERA_CONFIG,indent=2)+'\n')
