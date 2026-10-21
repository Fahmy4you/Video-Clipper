from typing import Literal
from uuid import uuid5,NAMESPACE_URL
from pydantic import BaseModel,Field,ConfigDict,model_validator
from .editorial import caption_groups
RESOLUTIONS={'9:16':(1080,1920),'16:9':(1920,1080),'1:1':(1080,1080),'4:5':(1080,1350),'4:3':(1440,1080)}
Ratio=Literal['9:16','16:9','1:1','4:5','4:3']
class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
class VisualStyle(Strict):
    x:float=Field(default=.5,ge=0,le=1)
    y:float=Field(default=.84,ge=0,le=1)
    width:float=Field(default=.88,gt=0,le=2)
    height:float=Field(default=.2,gt=0,le=2)
    rotation:float=Field(default=0,ge=-360,le=360)
    opacity:float=Field(default=1,ge=0,le=1)
    font:Literal['DejaVu Sans','Liberation Sans','Poppins']='DejaVu Sans'
    size:int=Field(default=62,ge=12,le=180)
    color:str=Field(default='#FFFFFF',pattern=r'^#[0-9A-Fa-f]{6}$')
    highlight:str=Field(default='#5EEAD4',pattern=r'^#[0-9A-Fa-f]{6}$')
    outline:float=Field(default=3,ge=0,le=12)
    align:Literal['left','center','right']='center'
    karaoke:bool=True
class FrameWord(Strict):
    id:str=Field(max_length=100)
    start:int=Field(ge=0)
    end:int=Field(gt=0)
    text:str=Field(max_length=150)
    @model_validator(mode='after')
    def ordered(self):
        if self.end<=self.start:raise ValueError('Durasi kata tidak valid.')
        return self
class Caption(Strict):
    id:str=Field(max_length=100)
    start:int=Field(ge=0)
    end:int=Field(gt=0)
    words:list[FrameWord]=Field(default_factory=list,max_length=200)
    style:VisualStyle|None=None
    @model_validator(mode='after')
    def ordered(self):
        if self.end<=self.start:raise ValueError('Durasi subtitle tidak valid.')
        if any(w.start<self.start or w.end>self.end for w in self.words):raise ValueError('Kata di luar blok subtitle.')
        return self
class Overlay(Strict):
    id:str=Field(max_length=100)
    kind:Literal['text','image']
    start:int=Field(ge=0)
    end:int=Field(gt=0)
    text:str=Field(default='',max_length=2000)
    asset_id:str|None=None
    layer:int=Field(default=1,ge=0,le=100)
    style:VisualStyle=Field(default_factory=VisualStyle)
    @model_validator(mode='after')
    def valid(self):
        if self.end<=self.start:raise ValueError('Durasi overlay tidak valid.')
        if self.kind=='image' and not self.asset_id:raise ValueError('Gambar belum dipilih.')
        return self
class Transform(Strict):
    legacy_center:bool=False
    mode:Literal['fit','fill','split']='fit'
    x:float=Field(default=.5,ge=0,le=1)
    y:float=Field(default=.5,ge=0,le=1)
    scale:float=Field(default=1,ge=1,le=4)
    b:float=Field(default=.7,ge=0,le=1)
class Fade(Strict):
    in_frames:int=Field(default=0,ge=0)
    out_frames:int=Field(default=0,ge=0)
    span:int=Field(default=0,ge=0)
    offset:int=Field(default=0,ge=0)
class Transition(Strict):
    kind:Literal['black','crossfade','none']='black'
    frames:int=Field(default=9,ge=0,le=90)
class Broll(Strict):
    id:str=Field(max_length=100)
    asset_id:str=Field(max_length=36)
    start:int=Field(ge=0)
    end:int=Field(gt=0)
    source_in:int=Field(default=0,ge=0)
    reason:str=Field(default='',max_length=2000)
    transform:Transform=Field(default_factory=lambda:Transform(mode='fill'))
    transition_in:Transition=Field(default_factory=Transition)
    transition_out:Transition=Field(default_factory=Transition)
    @model_validator(mode='after')
    def valid(self):
        from uuid import UUID
        UUID(self.asset_id)
        if self.end<=self.start:raise ValueError('Durasi sisipan tidak valid.')
        return self
class AudioItem(Strict):
    id:str=Field(max_length=100)
    asset_id:str=Field(max_length=36)
    start:int=Field(ge=0)
    end:int=Field(gt=0)
    source_in:int=Field(default=0,ge=0)
    volume:float=Field(default=.5,ge=0,le=1)
    fade:Fade=Field(default_factory=Fade)
    @model_validator(mode='after')
    def valid(self):
        from uuid import UUID
        UUID(self.asset_id)
        if self.end<=self.start:raise ValueError('Durasi audio tidak valid.')
        return self
class Segment(Strict):
    id:str=Field(max_length=100)
    source_in:int=Field(ge=0)
    duration:int=Field(gt=0)
    transform:Transform=Field(default_factory=Transform)
    captions:list[Caption]=Field(default_factory=list,max_length=2000)
    overlays:list[Overlay]=Field(default_factory=list,max_length=100)
    audio:list[AudioItem]=Field(default_factory=list,max_length=50)
    broll:list[Broll]=Field(default_factory=list,max_length=100)
    excluded_word_ids:list[str]=Field(default_factory=list,max_length=10000)
    @model_validator(mode='after')
    def bounds(self):
        items=[*self.captions,*self.overlays,*self.audio,*self.broll]
        ordered=sorted(self.broll,key=lambda b:b.start)
        if any(a.end>b.start for a,b in zip(ordered,ordered[1:])):raise ValueError("Sisipan tidak boleh tumpang tindih.")
        if any(x.end>self.duration for x in items):raise ValueError('Elemen melampaui potongan video.')
        ids=[x.id for x in items]
        if len(ids)!=len(set(ids)):raise ValueError('ID elemen harus unik.')
        return self
class EditPlanV2(Strict):
    version:Literal[2]=2
    fps:Literal[30]=30
    source_volume:float=Field(default=1,ge=0,le=1)
    source_fade:Fade=Field(default_factory=Fade)
    segments:list[Segment]=Field(min_length=1,max_length=200)
    subtitle_style:VisualStyle=Field(default_factory=VisualStyle)
    @model_validator(mode='after')
    def unique(self):
        ids=[s.id for s in self.segments]
        if len(ids)!=len(set(ids)):raise ValueError('ID potongan harus unik.')
        return self
def stable(value):return str(uuid5(NAMESPACE_URL,value))
def upgrade_plan(plan,key='legacy'):
    if plan.get('version')==2:return EditPlanV2.model_validate(plan).model_dump()
    oldstyle=plan.get('style',{})
    style=VisualStyle(**{k:v for k,v in oldstyle.items() if k in VisualStyle.model_fields},y=1-(oldstyle.get('margin',180)+oldstyle.get('size',62)/2)/1920)
    segments=[];layouts=plan.get('layouts') or [{'start':0,'mode':'fit','a':.3,'b':.7}]
    total=max(1,round((plan['end']-plan['start'])*30));base=round(plan['start']*30)
    for i,l in enumerate(layouts):
        start=round(l['start']*30);end=round(layouts[i+1]['start']*30) if i+1<len(layouts) else total
        if end<=start:continue
        words=[]
        for j,w in enumerate(plan.get('words',[])):
            a=max(start,round(w['start']*30));b=min(end,round(w['end']*30))
            if b>a:words.append({'id':f'w-{base+round(w["start"]*30)}-{j}','start':a-start,'end':b-start,'text':w['text']})
        groups=caption_groups([dict(w,start=w['start']/30,end=w['end']/30) for w in words]);captions=[]
        for j,g in enumerate(groups):
            ws=[dict(w,start=round(w['start']*30),end=round(w['end']*30)) for w in g]
            captions.append({'id':stable(f'{key}-caption-{i}-{j}'),'start':ws[0]['start'],'end':ws[-1]['end'],'words':ws})
        mode=l['mode'];x=l.get('a',.3) if mode!='b' else l.get('b',.7)
        segments.append({'id':stable(f'{key}-segment-{i}'),'source_in':base+start,'duration':end-start,'captions':captions,'transform':{'mode':'fit' if mode=='fit' else 'split' if mode=='split' else 'fill','x':.5 if mode=='fit' else x,'b':l.get('b',.7),'legacy_center':mode!='fit'}})
    return EditPlanV2(segments=segments,subtitle_style=style).model_dump()
