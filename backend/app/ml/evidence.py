"""Select an original-text excerpt using normalized token offsets."""
import re
import unicodedata

def lexical_excerpt(text, tokens, limit=360):
    normalized=[]; offsets=[]
    for position,char in enumerate(text):
        part=unicodedata.normalize('NFKC',char).casefold().replace('ё','е')
        normalized.extend(part); offsets.extend([position]*len(part))
    searchable=''.join(normalized)
    searchable=re.sub(r'\b1c\b','1с',searchable)
    positions=[]
    for token in tokens:
        match=re.search(re.escape(token),searchable)
        if match and match.start()<len(offsets):positions.append(offsets[match.start()])
    start=max(0,min(positions)-100) if positions else 0
    return text[start:start+limit]