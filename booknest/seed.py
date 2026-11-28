BOOKS = [
    ('Pride and Prejudice', 'Jane Austen', 'Literature', 1813, '12.50',
     'Family, first impressions, and changing judgments in English society.'),
    ('Alice in Wonderland', 'Lewis Carroll', "Children's", 1865, '9.95',
     'A curious girl explores a strange world of puzzles and imagination.'),
    ('The Adventures of Sherlock Holmes', 'Arthur Conan Doyle', 'Mystery', 1892, '14.00',
     'A detective and his friend investigate mysteries through observation.'),
    ('Frankenstein', 'Mary Shelley', 'Science Fiction', 1818, '13.25',
     'An ambitious scientist confronts the consequences of creating life.'),
    ('The Time Machine', 'H. G. Wells', 'Science Fiction', 1895, '11.00',
     'A traveler examines society, time, and an unfamiliar future.'),
]


def populate(service):
    with service.store.transaction() as s:
        if s['books']:
            return
        for n, (title, author, category, year, price, description) in enumerate(BOOKS, 1):
            s['books'].append({
                'id': f'book-{n}', 'title': title, 'author': author, 'category': category,
                'year': year, 'price': service.money(price), 'description': description,
                'tags': category, 'active': True, 'created': f'2026-01-0{n}T00:00:00+00:00',
                'cover': '', 'figures': [], 'list_override': '',
                'chapters': [
                    {'number': 1, 'paragraphs': [f'Demonstration passage for {title}. '
                     f'{description} This is sample text, not the original book.']},
                    {'number': 2, 'paragraphs': ['Demonstration chapter two: new questions arise and '
                     'the characters reconsider their first impressions. This is sample text.']},
                ],
            })
        s['taboo_words'] = [{'word': 'idiot'}, {'word': 'stupid'}]
