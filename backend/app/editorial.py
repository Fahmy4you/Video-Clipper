
"""Deterministic timing/readability improvements independent of the AI provider."""
def caption_groups(words,max_words=5,max_chars=36,max_duration=2.8,pause=.65):
    group=[]
    for word in words:
        chars=sum(len(w['text'].strip())+1 for w in group)+len(word['text'].strip())
        if group and (len(group)>=max_words or chars>max_chars or word['end']-group[0]['start']>max_duration or word['start']-group[-1]['end']>pause):
            yield group;group=[]
        group.append(word)
        if word['text'].strip().endswith(('.', '!', '?')):
            yield group;group=[]
    if group:yield group

def align_highlight(start,end,words,duration):
    """Expand a proposed cut to whole-word boundaries without losing the intended first/last word."""
    covered=[w for w in words if w['end']>start and w['start']<end]
    if not covered:return start,end
    start=min(start,covered[0]['start'])
    end=max(end,covered[-1]['end'])
    return max(0,round(start-.08,3)),min(duration,round(end+.12,3))
