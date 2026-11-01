"""Frame-exact subtitle visibility and transform, mirrored in subtitlePresentation.ts."""
def presentation(caption,style,frame):
    words=caption['words'];start=caption['start'];end=caption['end']
    if style.get('subtitle_mode','sentence')=='word':
        words=next(([w] for w in words if w['start']<=frame<w['end']),[])
        if not words:return [],1
        start,end=words[0]['start'],words[0]['end']
    scale=1.
    if style.get('subtitle_animation')=='soft_zoom':
        phase=min(4,(end-start-1)//2)
        if phase>0:
            x=frame-start;remaining=end-1-frame
            if x<phase:scale=.9+.1*(1-(1-x/phase)**3)
            elif remaining<phase:scale=.96+.04*(1-(1-remaining/phase)**3)
    return words,scale

def change_points(caption,style):
    points={caption['start'],caption['end']}
    word_mode=style.get('subtitle_mode')=='word'
    if style.get('karaoke') or word_mode:points.update(w['start'] for w in caption['words'])
    if word_mode:points.update(w['end'] for w in caption['words'])
    if style.get('subtitle_animation')=='soft_zoom':
        spans=[(w['start'],w['end']) for w in caption['words']] if word_mode else [(caption['start'],caption['end'])]
        for start,end in spans:
            phase=min(4,(end-start-1)//2)
            points.update(range(start,start+phase+1));points.update(range(end-phase-1,end+1))
    return points
