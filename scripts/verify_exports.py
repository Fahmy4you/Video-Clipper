import json, subprocess
from pathlib import Path
qa=Path('storage/qa/video-test')
report=json.loads((qa/'exports.json').read_text())
for item in report:
    result=subprocess.run(['ffmpeg','-v','error','-threads','2','-i',item['path'],'-f','null','-'],capture_output=True)
    if result.returncode or result.stderr:raise RuntimeError('Decode failed: '+item['title'])
    item['full_decode_passed']=True
    print('Full decode passed:',item['title'],flush=True)
(qa/'exports.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
