"""Canonical hashtags shared by API validation and Mix candidate selection."""
import re
import unicodedata
from typing import Annotated
from pydantic import AfterValidator, Field

def normalize_tags(values):
    result=[]
    for value in values:
        tag=unicodedata.normalize('NFKC',value).strip().lstrip('#').casefold().replace('-', '_')
        if not re.fullmatch(r'\w{1,50}',tag):
            raise ValueError('Hashtag memakai 1–50 huruf, angka, atau underscore tanpa spasi.')
        if tag not in result:result.append(tag)
    return result
Hashtags=Annotated[list[str],Field(max_length=30),AfterValidator(normalize_tags)]

def filter_library(library,tags):
    wanted=set(tags)
    return [a for a in library if not wanted or wanted.issubset(a.get('hashtags',[]))]
