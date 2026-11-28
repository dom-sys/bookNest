import re

TRANSLATE = str.maketrans({'0': 'o', '1': 'i', '3': 'e', '4': 'a', '@': 'a', '$': 's'})
TOKEN = re.compile(r'[\w@$]+', re.UNICODE)


def normalize(word):
    return re.sub(r'(.)\1+', r'\1', word.lower().translate(TRANSLATE))


def filter_comment(text, taboo):
    words = {normalize(w.strip()) for w in taboo if w.strip()}
    count = 0
    def replace(match):
        nonlocal count
        if normalize(match.group()) in words:
            count += 1
            return '*' * len(match.group())
        return match.group()
    return TOKEN.sub(replace, text), count
