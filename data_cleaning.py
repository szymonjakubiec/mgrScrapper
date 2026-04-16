import re
from bs4 import BeautifulSoup

def clean_readme(readme_text):
    # 1. Usuń bloki kodu (``` ... ```)
    readme_text = re.sub(r'```.*?```', '', readme_text, flags=re.DOTALL)
    # 2. Usuń inline code (`...`)
    readme_text = re.sub(r'`.*?`', '', readme_text)
    # 3. Usuń tagi HTML
    readme_text = BeautifulSoup(readme_text, "html.parser").get_text()
    # 4. Usuń linki Markdown [tekst](url)
    readme_text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', readme_text)
    # 5. Usuń znaki specjalne Markdown (#, *, -, etc.)
    readme_text = re.sub(r'[#\*_\-\>\d\.]+', ' ', readme_text)
    # 6. Usuń nadmiarowe spacje
    readme_text = re.sub(r'\s+', ' ', readme_text).strip()
    return readme_text