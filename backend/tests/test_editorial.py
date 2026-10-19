
from app.editorial import caption_groups,align_highlight
def w(start,end,text):return dict(start=start,end=end,text=text)
def test_caption_pause_and_sentence_boundaries():
    words=[w(0,.3,'Mulai'),w(.3,.7,'sekarang.'),w(.8,1,'Ya'),w(3,3.5,'berikutnya')]
    assert [[x['text'] for x in g] for g in caption_groups(words)]==[['Mulai','sekarang.'],['Ya'],['berikutnya']]
def test_caption_long_words_split_before_overflow():
    groups=list(caption_groups([w(0,.5,'mempertimbangkan'),w(.5,1,'ketidakpastian'),w(1,1.5,'keputusan')]))
    assert len(groups)==2
    assert max(len(' '.join(w['text'] for w in g)) for g in groups)<=36
def test_cut_expands_to_word_boundaries_and_stays_in_source():
    start,end=align_highlight(.2,1.5,[w(0,.4,'satu'),w(.5,2,'dua')],2)
    assert start==0 and end==2
def test_caption_duration_limit():
    groups=list(caption_groups([w(0,1,'satu'),w(1,2,'dua'),w(2,3,'tiga')]))
    assert len(groups)==2
