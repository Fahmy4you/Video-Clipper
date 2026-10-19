from PIL import Image,ImageDraw
from pathlib import Path
p=Path('storage/qa/visual-editor');p.mkdir(parents=True,exist_ok=True)
im=Image.new('RGBA',(200,100),(0,0,0,0));d=ImageDraw.Draw(im);d.rounded_rectangle((10,10,190,90),radius=20,fill=(40,200,120,180));im.save(p/'qa-transparent.png')
