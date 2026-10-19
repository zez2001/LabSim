"""Source/B/query-C sections and labelled worst support point (sampled)."""
import json,numpy as np,trimesh
from demos.lab_cuvette_ext02.audit import Union,meshes
from demos.lab_cuvette_ext02.build import ROOT,source_mesh
from demos.lab_cuvette_external.run import write

def create():
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 doc=ROOT/'docs/lab_cuvette_loading/V0_ext02';fig,axes=plt.subplots(2,2,figsize=(12,10));details={};A=source_mesh()
 for row,name in enumerate(['control193','walls28_mm']):
  p=ROOT/'outputs/lab_cuvette_loading/V0_ext02/contact_repro01'/name;B=Union(meshes(json.load(open(p/'B_input.json'))));raw=json.load(open(p/'C_cooking_query.json'))['hulls'];C=Union(meshes(raw));audit=json.load(open(p/'geometry_audit.json'));worst=audit['comparisons']['A_missing_C']['worst_support'];point=np.array(worst['point_m']);details[name]=worst
  x=np.linspace(-.0076,.0076,360);xx,yy=np.meshgrid(x,x);g=np.c_[xx.ravel(),yy.ravel(),np.full(xx.size,.00005)]
  for obj,color,label in [(A,'black','A source'),(B,'tab:blue','B input union'),(C,'tab:red','query C union')]:
   mask=obj.contains(g).reshape(xx.shape);axes[row,0].contour(xx*1000,yy*1000,mask,levels=[.5],colors=[color],linewidths=1.0);axes[row,0].plot([],[],color=color,label=label)
   mesh=obj if obj is A else obj.mesh
   seg=trimesh.intersections.mesh_plane(mesh,[0,1,0],[0,point[1],0])
   for s in seg:axes[row,1].plot(s[:,0]*1000,s[:,2]*1000,color=color,lw=.7,alpha=.7)
  axes[row,0].scatter(point[0]*1000,point[1]*1000,c='orange',s=25);axes[row,0].set_title(f'{name}: z=0.05 mm union contours\nimage grid ~0.042 mm; NOT measurement resolution');axes[row,0].set_xlabel('X (mm)');axes[row,0].set_ylabel('Y (mm)');axes[row,0].set_aspect('equal');axes[row,0].legend(fontsize=8)
  axes[row,1].scatter(point[0]*1000,point[2]*1000,c='orange',s=25);axes[row,1].set_title(f'Worst sampled support point: {worst["distance_m"]*1000:.4f} mm\nY={point[1]*1000:.6f} mm; raw part section lines');axes[row,1].set_xlabel('X (mm)');axes[row,1].set_ylabel('Z (mm)');axes[row,1].set_ylim(-.1,.6);axes[row,1].set_xlim(point[0]*1000-.6,point[0]*1000+.6)
  for ax in axes[row]:ax.grid(alpha=.2)
 fig.suptitle('Collision debug: source vs authored material blocks vs PhysX cooking query\nC query is not a complete native actor mesh export');fig.tight_layout();fig.savefig(doc/'collision_debug.png',dpi=170);write(doc/'worst_support_points.json',details)
if __name__=='__main__':create()
