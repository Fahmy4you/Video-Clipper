"""Visible spans and stable pair-bound transitions, independent of stored segment slicing."""
from copy import deepcopy
NONE={"kind":"none","frames":0,"sound":"none","sound_volume":1}
def spans(plan):
    out=[];offset=0
    for s in plan["segments"]:
        cursor=0
        def podcast(a,b):
            if b>a:out.append(dict(key="p:"+s["id"],kind="podcast",start=offset+a,end=offset+b,source_in=s["source_in"]+a,transform=s["transform"],segment_id=s["id"]))
        for b in sorted(s.get("broll",[]),key=lambda b:b["start"]):
            podcast(cursor,b["start"])
            item=dict(b,key="b:"+(b.get("visual_id") or b["id"]),kind="broll",start=offset+b["start"],end=offset+b["end"],segment_id=s["id"])
            if out and out[-1]["key"]==item["key"] and out[-1]["end"]==item["start"] and out[-1]["source_in"]+out[-1]["end"]-out[-1]["start"]==item["source_in"] and out[-1]["transform"]==item["transform"]:
                out[-1].update(end=item["end"],transition_out=item.get("transition_out",NONE))
            else:out.append(item)
            cursor=b["end"]
        podcast(cursor,s["duration"]);offset+=s["duration"]
    return out

def boundaries(plan):
    rows=spans(plan);stored={t["id"]:t for t in plan.get("transitions",[])}
    pairs=[(None,rows[0])]+list(zip(rows,rows[1:]))+[(rows[-1],None)] if rows else []
    out=[]
    for left,right in pairs:
        lk=left["key"] if left else "start";rk=right["key"] if right else "end"
        if lk==rk:continue
        key=lk+"|"+rk
        edge=NONE
        if plan.get("transition_version")==1:edge=stored.get(key,{}).get("value",NONE)
        else:
            a=left.get("transition_out",NONE) if left and left["kind"]=="broll" else NONE
            b=right.get("transition_in",NONE) if right and right["kind"]=="broll" else NONE
            edge=a if a.get("kind")!="none" or a.get("sound","none")!="none" else b
        out.append(dict(id=key,left=lk,right=rk,frame=right["start"] if right else left["end"],value=dict(edge),before=left,after=right))
    return out

def normalize(plan):
    p=deepcopy(plan)
    # Legacy cross-segment fragments share visual identity when source and framing continue.
    previous=None;offset=0;seen={}
    for s in p["segments"]:
        for b in sorted(s.get("broll",[]),key=lambda b:b["start"]):
            start=offset+b["start"];end=offset+b["end"]
            def continuous(old):
                return old and old[2]==start and old[0]["asset_id"]==b["asset_id"] and old[0]["source_in"]+old[0]["end"]-old[0]["start"]==b["source_in"] and old[0]["transform"]==b["transform"]
            if not b.get("visual_id"):
                same=previous and previous[1]!=s["id"] and continuous(previous) and previous[0]["transition_out"]["kind"]=="none" and b["transition_in"]["kind"]=="none"
                b["visual_id"]=previous[0]["visual_id"] if same else b["id"]
            if b["visual_id"] in seen and not continuous(seen[b["visual_id"]]):b["visual_id"]=b["id"]
            previous=(b,s["id"],end);seen[b["visual_id"]]=previous
        offset+=s["duration"]
    edges=boundaries(p)
    p["transition_version"]=1
    p["transitions"]=[{k:e[k] for k in ("id","left","right")} | {"value":e["value"]} for e in edges]
    return p

def events(plan,asset_frames=None):
    edges=boundaries(plan);duration=sum(s["duration"] for s in plan["segments"])
    result=[]
    for e in edges:
        f=e["frame"];value=e["value"];requested=value.get("frames",0)/2
        distance=min([abs(f-x["frame"])/2 for x in edges if x["frame"]!=f] or [0])
        half=int(min(requested,f,duration-f,distance));kind=value["kind"];fallback=False
        if kind=="crossfade" and half:
            for span in (e["before"],e["after"]):
                if not span:kind="black";fallback=True;break
                start=span["source_in"]+f-half-span["start"];end=start+half*2
                limit=(asset_frames or {}).get(span.get("asset_id","podcast"))
                if start<0 or limit is not None and end>limit:kind="black";fallback=True;break
        result.append(dict(e,half=half if kind!="none" else 0,requested=requested,kind=kind,fallback=fallback))
    return result

def validate_minimum(new,old=None):
    def lengths(p):
        rows={s["id"]:s["duration"] for s in p["segments"]}
        groups={}
        for s in p["segments"]:
            for b in s.get("broll",[]):
                key=b.get("visual_id") or b["id"];groups[key]=groups.get(key,0)+b["end"]-b["start"]
        return rows,groups
    old_rows,old_b=lengths(normalize(old)) if old else ({},{})
    for current,prior in zip(lengths(normalize(new)),(old_rows,old_b)):
        if any(n<30 and prior.get(k)!=n for k,n in current.items()):
            raise ValueError("Setiap hasil potongan video minimal 1 detik.")
