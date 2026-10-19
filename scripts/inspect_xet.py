import json,re
from pathlib import Path
p=max(Path.home().joinpath('.cache/huggingface/xet/logs').glob('*.log'),key=lambda p:p.stat().st_mtime)
for line in p.read_text().splitlines()[-8:]:
    d=json.loads(line);fields=d.get('fields',{})
    message=re.sub(r'https?[^\s"\)]+','[url]',str(fields.get('message','')))
    print(d.get('level'),message[:500])
