from pathlib import Path
import subprocess,json,hashlib,shutil
ROOT=Path(__file__).resolve().parent
SOURCE=Path('/home/wujing/Desktop/来自远程/20261013')
VIDEO=SOURCE/'5afd3b2ffa3632d9c4599d8051018895_raw.mp4'
frames=[0,12,24,36,48,72,96,120,132,136,140,142]
records=[]
for n in frames:
    name=f'frame_{n:03d}_t{n/2.4:06.3f}.jpg'
    out=ROOT/'frames'/name
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i',str(VIDEO),'-vf',f'select=eq(n\\,{n})','-frames:v','1','-q:v','2','-y',str(out)],check=True)
    records.append({'video_frame_index':n,'encoded_time_s':n/2.4,'path':str(out.relative_to(ROOT)),'sha256':hashlib.sha256(out.read_bytes()).hexdigest()})
for p in sorted(SOURCE.glob('*.jpg')):
    out=ROOT/'photos'/p.name
    shutil.copyfile(p,out)
    records.append({'source':str(p),'path':str(out.relative_to(ROOT)),'sha256':hashlib.sha256(out.read_bytes()).hexdigest()})
metadata=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(VIDEO)]))
manifest={'video_source':str(VIDEO),'video_sha256':hashlib.sha256(VIDEO.read_bytes()).hexdigest(),'metadata':metadata,'frames_and_photos':records,'note':'Frames are exact decoded integer frame indices, JPEG encoding only. Encoded time is not original control time. No photographic reconstruction or physical measurement.'}
(ROOT/'source_media_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')

# Plain crops / nearest content from exact frames, with explicitly stated rescaling.
crops=[('frame_000_t00.000.jpg','source_rack_t0_crop.png','crop=340:270:780:690,scale=1360:1080'),('frame_142_t59.167.jpg','chamber_final_right_crop.png','crop=1350:720:2350:360'),('frame_000_t00.000.jpg','right_frame_000.jpg','crop=1920:1080:1920:0'),('frame_142_t59.167.jpg','right_frame_142.jpg','crop=1920:1080:1920:0'),('frame_036_t15.000.jpg','source_rack_t15_hand_crop.jpg','crop=1180:700:1940:380')]
for src,out,flt in crops:
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i',str(ROOT/'frames'/src),'-vf',flt,'-frames:v','1','-y',str(ROOT/'frames'/out)],check=True)
