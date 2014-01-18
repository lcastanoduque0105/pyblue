# Four lines are specified for each publication
# Authors, Title, Url, Journal

FIELD_COUNT = 4

TEXT = """

John Doe, Jane Doe
Chronic properties of the the doubly sublimated tio-timolin
http://www.psu.edu
Natural Sciences, 2, 2014

Mr Smith, Ms. Smith Doe
Novel insights into something
http://www.nd.edu
Scientific Naturals, 8, 2012

Senor Gonzales, Senorita Bonita
Lo no puedo anque quiero
http://http://www.spanishdict.com/
El Gato, 89, 2014

"""

def publications():
    lines = TEXT.splitlines()
    lines = map(lambda x: x.strip(), lines)
    lines = filter(None, lines)
    group = [iter(lines)] * FIELD_COUNT
    return zip(*group)
