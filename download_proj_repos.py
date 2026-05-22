import asyncio
import httpx
import asyncpg
import datetime
import json
import os
from dotenv import load_dotenv

from mgrScrapper.data_cleaning import extract_project_description

load_dotenv()
gh_token = os.getenv("GITHUB_TOKEN")

# Twój token do GitHub API (wymagany do wyszukiwania)
GITHUB_TOKEN = gh_token
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

EXCLUDED_TOPICS = [
    "library", "education", "learn", "framework",
    "educationbook", "learning", "tutorial", "course",
    "awesome", "book", "example", "sdk"
]

# async def init_db():
#     """Łączy się z Twoją bazą w Dockerze (założone domyślne porty i poświadczenia z docker-compose)"""
#     conn = await asyncpg.connect(
#         user='your_user', password='your_password',
#         database='your_db', port='5433'
#     )
#     # Tworzymy tabelę, jeśli nie istnieje
#     await conn.execute('''
#                        CREATE TABLE IF NOT EXISTS repositories
#                        (
#                            id              SERIAL PRIMARY KEY,
#                            full_name       VARCHAR(255) UNIQUE,
#                            url             VARCHAR(255),
#                            language        VARCHAR(50),
#                            readme_text     TEXT,
#                            dependency_file TEXT,
#                            is_processed    BOOLEAN DEFAULT FALSE
#                        )
#                        ''')
#     return conn


async def fetch_raw_file(client, full_name, default_branch, file_path):
    """Pobiera plik omijając limity API, używając raw.githubusercontent.com"""
    url = f"https://raw.githubusercontent.com/{full_name}/{default_branch}/{file_path}"
    try:
        response = await client.get(url, timeout=10.0)
        if response.status_code == 200:
            return response.text
        return None
    except Exception:
        return None


async def search_repositories_by_date(client, language, start_date, end_date):
    """Wyszukuje repozytoria w określonym oknie czasowym, aby obejść limit 1000 wyników"""

    exclusions = " ".join([f"-topic:{topic}" for topic in EXCLUDED_TOPICS])
    query = f"language:{language} stars:>10 {exclusions} created:{start_date}..{end_date}"

    url = "https://api.github.com/search/repositories"

    repos = []
    page = 1
    max_pages = 1

    print(f"Start searching for max {100*max_pages} repos")

    while page <= max_pages:
        params = {
            "q": query,
            "per_page": 100,
            "page": page,
        }
        try:
            response = await client.get(url, params=params, headers=HEADERS, timeout=15.0)

            if response.status_code == 200:
                data = response.json()
                items = data.get("items", [])
                if not items:
                    print(f"No repos found on page {page}. Ending search.")
                    break

                for item in items:
                    repos.append({
                        "full_name": item["full_name"],
                        "html_url": item["html_url"],
                        "default_branch": item["default_branch"],
                        "language": language
                    })
                print(f"Downloaded {page}/{max_pages}, results: {len(items)}")
                page += 1

                await asyncio.sleep(2.5)

            elif response.status_code == 403:
                print("Limit API osiągnięty! Czekam 60 sekund...")
                await asyncio.sleep(60)
            else:
                # Warto logować też inne błędy (np. wciąż pojawiający się 422), by wiedzieć co nie gra
                print(f"Błąd API {response.status_code}: {response.text}")
                break

        except Exception as e:
            print(f"Błąd wyszukiwania: {e}")



    return repos

async def process_repository(client, repo):
    """Pobiera README i plik zależności, a następnie zapisuje do bazy"""
    full_name = repo["full_name"]
    branch = repo["default_branch"]
    lang = repo["language"]

    dep_file_name = "package.json" if lang == "JavaScript" else "pom.xml" if lang == "Java" else "requirements.txt"

    readme_task = fetch_raw_file(client, full_name, branch, "README.md")
    dep_task = fetch_raw_file(client, full_name, branch, dep_file_name)
    npmignore_task = fetch_raw_file(client, full_name, branch, ".npmignore")

    readme_content, dep_content, npm_file = await asyncio.gather(readme_task, dep_task, npmignore_task)

    if dep_content:
        if lang == "JavaScript" and dep_content:
            try:
                pkg = json.loads(dep_content)
                deps_count = len(pkg.get("dependencies", {}))
                devDeps_count = len(pkg.get("devDependencies", {}))

                if npm_file:
                    print(f"- {full_name}: Discarded, has .npmignore")
                    bad_dep_content.append(full_name)
                    return

                if deps_count + devDeps_count < 5:
                    print(f"- {full_name}: Discarded, too few dependencies - probably a small project or tutorial")
                    bad_dep_content.append(full_name)
                    return

                if any(key in pkg for key in ["types", "typings", "exports", "module"]):
                    print(f"- {full_name}: Discarded probably a library")
                    bad_dep_content.append(full_name)
                    return

                if any(word in full_name.lower() for word in
                       ["algorithm", "concept", "tutorial", "roadmap", "cheatsheet", "you-dont-need", "guide", "icons", "awesome", "collection", "bits", "starter", "framework", "interview", "course"]):
                    print(f"- {full_name}: Discarded, keyword match in name (tutorial/book)")
                    bad_dep_content.append(full_name)
                    return

            except json.JSONDecodeError:
                print(f"Error when parsing JSON for {full_name}")
                bad_dep_content.append(full_name)
                return

        try:
            # clean = extract_project_description(readme_content)
            good_dep_content.append(full_name)
            # with open("fil_results.txt", "a", encoding="utf-8") as f:
            #     f.write(f"{full_name}\n{clean}\n\n")
            # await db_conn.execute('''
            #                       INSERT INTO repositories (full_name, url, language, readme_text, dependency_file)
            #                       VALUES ($1, $2, $3, $4, $5)
            #                       ON CONFLICT (full_name) DO NOTHING
            #                       ''', full_name, repo["html_url"], lang, readme_content, dep_content)
            print(f"{full_name}: Verified and saved")
        except Exception as e:
            print(f"Błąd bazy dla {full_name}: {e}")
    else:
        no_dep_content.append(full_name)


async def main():

    # db_conn = await init_db()

    # connection limits
    limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)

    async with httpx.AsyncClient(limits=limits) as client:
        start_date = "2018-01-01"
        end_date = "2026-01-01"

        print(f"Szukam repozytoriów JavaScript z okresu {start_date} do {end_date}...")
        repos = await search_repositories_by_date(client, "JavaScript", start_date, end_date)

        # print(f"Znaleziono {len(repos)} repozytoriów. Rozpoczynam pobieranie plików...")


        # Tworzymy zadania do współbieżnego pobierania plików
        tasks = [process_repository(client, repo) for repo in repos]

        # Uruchamiamy zadania paczkami (np. po 20 naraz), aby nie obciążyć GitHuba
        chunk_size = 20
        for i in range(0, len(tasks), chunk_size):
            await asyncio.gather(*tasks[i:i + chunk_size])
            await asyncio.sleep(1)  # Krótki oddech dla serwerów GitHuba

        good_dep_content_sort = sorted(good_dep_content)
        bad_dep_content_sort = sorted(bad_dep_content)
        no_dep_content_sort = sorted(no_dep_content)

        print(f"good repos: {len(good_dep_content)}")
        print(f"bad repos: {len(bad_dep_content)}")
        print(f"no content repos: {len(no_dep_content)}")

        with open("repos_results-0 attempt2.txt", "a") as f:
            f.write(f"good repos: {len(good_dep_content_sort)}\n")
            for repo in good_dep_content_sort:
                f.write(f"{repo}\n")
            f.write(f"\n\nbad repos: {len(bad_dep_content_sort)}\n\n")
            for repo in bad_dep_content_sort:
                f.write(f"{repo}\n")
            f.write(f"\n\nno content repos: {len(no_dep_content_sort)}\n\n")
            for repo in no_dep_content_sort:
                f.write(f"{repo}\n")


if __name__ == "__main__":
    no_dep_content = []
    bad_dep_content = []
    good_dep_content = []

    asyncio.run(main())