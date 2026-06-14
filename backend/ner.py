import yake
import re

extractor = yake.KeywordExtractor(
    lan='en',
    n=2,
    top=20
)

BLOCKED_TERMS = {
    'subscribe',
    'subscribed',
    'like',
    'share',
    'comment',
    'comments',
    'notification',
    'notifications',
    'bell',
    'channel',
    'youtube',
    'video',
    'watch',
    'views',
    'playlist',
    'shorts',
    'live',
    'thanks',
    'thank',
    'follow',
    'download',
    'upload',
    'skip',
    'ad',
    'ads',
    'sponsor',
    'sponsored',
    'absorbs',
    'converts',
    'minimizes',
    'using',
    'uses',
}

BLOCKED_PHRASES = {
    'like share',
    'share subscribe',
    'like subscribe',
    'subscribe channel',
    'youtube channel',
    'click subscribe',
    'press bell',
    'notification bell',
}

def is_useful_term(term):
    normalized = re.sub(r'[^a-z0-9 ]+', ' ', term.lower())
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    if not normalized or len(normalized) < 3:
        return False
    if normalized in BLOCKED_PHRASES:
        return False
    words = normalized.split()
    if any(word in BLOCKED_TERMS for word in words):
        return False
    return any(char.isalpha() for char in normalized)

def extract_entities(text):
    if not text or len(text.strip()) < 10:
        return []

    # YAKE for technical concepts and keywords
    keywords = [
        {'entity': kw, 'label': 'KEYWORD'}
        for kw, score in extractor.extract_keywords(text)
        if is_useful_term(kw)
    ]

    # regex for proper nouns - people, places, organizations
    proper = re.findall(r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b', text)
    for noun in set(proper):
        if is_useful_term(noun) and noun not in [k['entity'] for k in keywords]:
            keywords.append({'entity': noun, 'label': 'PROPER_NOUN'})

    return keywords[:8]
