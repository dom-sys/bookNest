from PIL import Image, UnidentifiedImageError


def dhash(path):
    with Image.open(path) as image:
        if image.format not in ('JPEG', 'PNG', 'WEBP'):
            raise ValueError('Choose a JPG, PNG, or WEBP image.')
        image = image.convert('L').resize((9, 8))
        pixels = list(image.getdata())
    return sum((pixels[y*9+x] > pixels[y*9+x+1]) << (y*8+x) for y in range(8) for x in range(8))


def rank_images(path, books, root):
    try:
        query = dhash(path)
    except (OSError, UnidentifiedImageError):
        raise ValueError('Cannot read this image. Choose a JPG, PNG, or WEBP file.') from None
    ranks = []
    for book in books:
        if not book.get('cover'):
            continue
        try:
            score = 1 - (query ^ dhash(root / book['cover'])).bit_count() / 64
        except (OSError, ValueError):
            continue
        ranks.append((book['id'], score))
    return sorted(ranks, key=lambda row: -row[1])
