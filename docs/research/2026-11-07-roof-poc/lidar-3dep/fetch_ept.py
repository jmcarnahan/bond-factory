import sys,json,time,io,requests,numpy as np,laspy
from pyproj import Transformer
proj,lon,lat,half,out=sys.argv[1],float(sys.argv[2]),float(sys.argv[3]),float(sys.argv[4]),sys.argv[5]
B='https://usgs-lidar-public.s3.amazonaws.com/'+proj+'/'
t0=time.time(); nbytes=0; nreq=0
s=requests.Session()
def get(u):
    global nbytes,nreq
    r=s.get(u,timeout=60); r.raise_for_status(); nbytes+=len(r.content); nreq+=1; return r.content
ept=json.loads(get(B+'ept.json'))
cube=ept['bounds']
to_utm=Transformer.from_crs(4326,32611,always_xy=True); utm_to_m=Transformer.from_crs(32611,3857,always_xy=True)
cx,cy=to_utm.transform(lon,lat)
x0,y0,x1,y1=cx-half,cy-half,cx+half,cy+half
cs=[utm_to_m.transform(x,y) for x,y in [(x0,y0),(x1,y0),(x0,y1),(x1,y1)]]
mx0,mx1=min(c[0] for c in cs),max(c[0] for c in cs); my0,my1=min(c[1] for c in cs),max(c[1] for c in cs)
def inter(key):
    d,x,y,z=key
    sx=(cube[3]-cube[0])/2**d; sy=(cube[4]-cube[1])/2**d
    a=cube[0]+x*sx; b=cube[1]+y*sy
    return a<=mx1 and a+sx>=mx0 and b<=my1 and b+sy>=my0
hier={}
def load_h(k):
    hier.update(json.loads(get(B+'ept-hierarchy/%s.json'%k)))
load_h('0-0-0-0')
want=[];stack=['0-0-0-0'];seen=set()
while stack:
    k=stack.pop()
    if k in seen: continue
    seen.add(k)
    key=tuple(int(v) for v in k.split('-'))
    if not inter(key): continue
    if k not in hier: continue
    n=hier[k]
    if n==-1:
        load_h(k)   # subtree hierarchy page
        n=hier.get(k,0)
    if n>0: want.append(k)
    d,x,y,z=key
    for dx in (0,1):
        for dy in (0,1):
            for dz in (0,1):
                c='%d-%d-%d-%d'%(d+1,2*x+dx,2*y+dy,2*z+dz)
                if c in hier: stack.append(c)
print('nodes',len(want),'maxdepth',max(int(k.split('-')[0]) for k in want),'hier_t',round(time.time()-t0,1),flush=True)
cols={k:[] for k in 'x y z cls inten rn nr gps ang'.split()}
for k in want:
    las=laspy.read(io.BytesIO(get(B+'ept-data/%s.laz'%k)))
    X=np.asarray(las.x);Y=np.asarray(las.y)
    m=(X>=mx0)&(X<=mx1)&(Y>=my0)&(Y<=my1)
    if not m.any(): continue
    ux,uy=to_utm_inv=Transformer.from_crs(3857,32611,always_xy=True).transform(X[m],Y[m])
    cols['x'].append(ux);cols['y'].append(uy);cols['z'].append(np.asarray(las.z)[m])
    cols['cls'].append(np.asarray(las.classification)[m]);cols['inten'].append(np.asarray(las.intensity)[m])
    cols['rn'].append(np.asarray(las.return_number)[m]);cols['nr'].append(np.asarray(las.number_of_returns)[m])
    cols['gps'].append(np.asarray(las.gps_time)[m]);cols['ang'].append(np.asarray(las.scan_angle)[m] if hasattr(las,'scan_angle') else np.zeros(m.sum()))
if not cols['x']:
    print('NO POINTS in box'); sys.exit(0)
A={k:np.concatenate(v) for k,v in cols.items()}
m=(A['x']>=x0)&(A['x']<=x1)&(A['y']>=y0)&(A['y']<=y1)
A={k:v[m] for k,v in A.items()}
np.savez_compressed(out,center=np.array([cx,cy]),**A)
print('fetch_seconds',round(time.time()-t0,1),'requests',nreq,'bytes',nbytes,'points',len(A['x']))
