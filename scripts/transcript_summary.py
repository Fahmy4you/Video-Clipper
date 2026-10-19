import json
from pathlib import Path
words=json.loads(Path('storage/projects/a6f2c6fa-b1a7-4473-92b9-1c8fec6dbc07/transcript.json').read_text())['words']
for t in range(0,1364,60):
    print(t, ' '.join(w['text'] for w in words if t<=w['start']<t+60))
