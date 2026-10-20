from pathlib import Path
import cv2,numpy as np,json
ROOT=Path(__file__).resolve().parent
im=cv2.imread(str(ROOT/'frames/source_rack_t0_crop.png'))
# Hand-picked corners of visible upper grid region in enlarged crop; projective aid only.
src=np.float32([[210,375],[650,130],[1000,585],[555,840]])
dst=np.float32([[0,0],[799,0],[799,799],[0,799]])
M=cv2.getPerspectiveTransform(src,dst)
out=cv2.warpPerspective(im,M,(800,800))
cv2.imwrite(str(ROOT/'frames/source_rack_manual_perspective_aid.png'),out)
(ROOT/'rack_perspective_aid.json').write_text(json.dumps({'source':'frames/source_rack_t0_crop.png','src_px':src.tolist(),'dst_px':dst.tolist(),'homography':M.tolist(),'warning':'Hand-picked projective image aid; no camera calibration, no metric reconstruction. Used only to count visible divisions; does not establish CAD dimensions.'},indent=2)+'\n')
