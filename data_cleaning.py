import re
import emoji
from bs4 import BeautifulSoup

# def clean_readme(readme_text):
#     # 1. Usuń bloki kodu (``` ... ```)
#     readme_text = re.sub(r'```.*?```', '', readme_text, flags=re.DOTALL)
#     # 2. Usuń inline code (`...`)
#     readme_text = re.sub(r'`.*?`', '', readme_text)
#     # 3. Usuń tagi HTML
#     readme_text = BeautifulSoup(readme_text, "html.parser").get_text()
#     # 4. Usuń linki Markdown [tekst](url)
#     readme_text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', readme_text)
#     # 5. Usuń znaki specjalne Markdown (#, *, -, etc.)
#     readme_text = re.sub(r'[#\*_\-\>\d\.]+', ' ', readme_text)
#     # 6. Usuń nadmiarowe spacje
#     readme_text = re.sub(r'\s+', ' ', readme_text).strip()
#     return readme_text

import re


def extract_project_description(readme_content: str) -> str:
    """
    Wydobywa główny opis projektu z zawartości pliku README z GitHuba.
    Ignoruje nagłówki, badge, tagi HTML oraz spis treści.

    :param readme_content: Zawartość pliku README.md w formie stringa.
    :return: Wyekstrahowany opis projektu.
    """
    if not isinstance(readme_content, str) or not readme_content.strip():
        return ""

    # 1. Usunięcie komentarzy HTML (często ukrywają notatki dla kontrybutorów)
    text = re.sub(r'', '', readme_content, flags=re.DOTALL)

    # 2. Usunięcie badge'y Markdown i linkowanych obrazków (np. [![Build Status](...)](...))
    text = re.sub(r'\[?!\[.*?\]\(.*?\)\]?\(.*?\)', '', text)

    # 3. Usunięcie zwykłych obrazków Markdown (np. ![Logo](url))
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)

    # 4. Usunięcie tagów HTML (np. <p align="center">, <img src="...">)
    text = re.sub(r'<[^>]+>', '', text)

    text = emoji.replace_emoji(text, replace='')

    text = text.strip()
    # Rozbicie na linie w celu analizy strukturalnej
    lines = text.split('\n')
    description_lines = []
    is_capturing = False

    for line in lines:
        stripped = line.strip()

        # Pomijanie pustych linii, chyba że już zaczęliśmy zbierać opis
        if not stripped:
            if is_capturing:
                # Pusta linia po tekście oznacza koniec akapitu.
                # Zazwyczaj pierwszy pełny akapit to właśnie celowy opis.
                break
            continue

        # Pomijanie nagłówków Markdown (np. # Project Name, ## Features)
        if stripped.startswith('#'):
            continue

        # Pomijanie list (np. spisy treści, listy funkcji na samej górze)
        if stripped.startswith('- ') or stripped.startswith('* ') or re.match(r'^\d+\.', stripped):
            if not is_capturing:
                continue
            else:
                break  # Zatrzymujemy, jeśli po opisie zaczyna się lista

        # Pomijanie separatorów poziomy i bloków kodu
        if stripped.startswith('---') or stripped.startswith('===') or stripped.startswith('```'):
            if is_capturing:
                break
            continue

        # Pomijanie tabel
        if stripped.startswith('|'):
            if is_capturing:
                break
            continue

        # HEURYSTYKA: Jeśli linia dotrwała do tego momentu, jest dość długa
        # i zawiera litery, uznajemy ją za początek opisu.
        # Wartość > 30 znaków odfiltrowuje krótkie, osierocone słowa (np. "Status", "WIP").
        if len(stripped) > 30 and re.search(r'[a-zA-Z]', stripped):
            is_capturing = True
            description_lines.append(stripped)

    # Połączenie zebranych linii w jeden spójny ciąg tekstu
    final_description = ' '.join(description_lines).strip()

    return final_description

mock_readme = """
<p align="center">
  <img src="logo.png">
</p>

# Uptime Kuma

[![Docker Pulls](https://img.shields.io/docker/pulls/louislam/uptime-kuma.svg)](https://hub.docker.com/r/louislam/uptime-kuma)
[![GitHub stars](https://img.shields.io/github/stars/louislam/uptime-kuma.svg)](https://github.com/louislam/uptime-kuma/stargazers)

📚It is a self-hosted monitoring tool like "Uptime Robot".
Uptime Kuma is designed to be fast, responsive, and easy to use.

## Features
* Monitoring HTTP(s) / TCP / HTTP(s) Keyword / Ping / DNS Record / Push / Steam Game Server / Docker Containers.
* Fancy, Reactive, Fast UI/UX.
"""

print("Wydobyty opis:")
print(extract_project_description(mock_readme))