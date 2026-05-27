import asyncio
import httpx
import asyncpg
import datetime
import json
import os
from dotenv import load_dotenv

from mgrScrapper.data_cleaning import extract_project_description

load_dotenv() 
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

EXCLUDED_TOPICS = [
    'api', 'awesome', 'book', 'challenge', 'course', 'education', 'educationbook', 'example',
    'framework', 'learn', 'learning', 'library', 'sdk', 'tutorial'
]

EXCLUDED_TITLEWORDS = [
    'algorithm', 'awesome', 'bits', 'cheatsheet', 'collection', 'concept', 'course', 'framework', 'guide',
            'icons', 'interview', 'roadmap', 'starter', 'tutorial', 'you-dont-need'
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

async def fetch_repo_tree_paths(client, full_name, default_branch, dep_filename):
    """
    Pobiera pełne drzewo plików repozytorium przez GitHub API.
    Wymaga podania brancha (np. 'main' lub 'master').
    """

    url = f"https://api.github.com/repos/{full_name}/git/trees/{default_branch}?recursive=1" # ?recursive=1 pobiera całe drzewo za jednym zapytaniem

    try:
        response = await client.get(url, headers=HEADERS, timeout=10.0)

        if response.status_code == 200:
            data = response.json()

            paths = []
            for item in data.get("tree", []):
                # Interesują nas tylko pliki ("blob")
                if item.get("type") == "blob":
                    path = item["path"]

                    if not path.endswith(dep_filename):
                        continue

                    parts = path.split('/')
                    depth = len(parts) - 1

                    if depth > 2:
                        continue

                    if any(part.startswith('.') for part in parts):
                        continue

                    paths.append(path)

            return paths

        elif response.status_code in (403, 429):
            print(f"Reached GitHub API limit while downloading tree: {full_name}!")
            return []

        else:
            print(f"Error {response.status_code} while downloading tree: {full_name}")
            return []

    except Exception as e:
        print(f"Exception while downloading tree {full_name}: {e}")
        return []



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
                print("Reached API limit! Waiting 60 seconds...")
                await asyncio.sleep(60)
            else:
                print(f"API error {response.status_code}: {response.text}")
                break

        except Exception as e:
            print(f"Searching error: {e}")

    return repos

async def process_repository(client, repo):
    """Pobiera README i plik zależności, a następnie zapisuje do bazy"""
    full_name = repo["full_name"]
    branch = repo["default_branch"]
    lang = repo["language"]

    if any(word in full_name.lower() for word in EXCLUDED_TITLEWORDS):
        print(f"- {full_name}: Discarded, keyword match in name (tutorial/book)")
        bad_dep_content.append(full_name)
        return

    dep_filename = "package.json" if lang == "JavaScript" else "pom.xml" if lang == "Java" else "requirements.txt"

    readme_task = fetch_raw_file(client, full_name, branch, "README.md")
    npmignore_task = fetch_raw_file(client, full_name, branch, ".npmignore")
    tree_task = fetch_repo_tree_paths(client, full_name, branch, dep_filename)

    readme_content, npm_file, valid_dep_paths = await asyncio.gather(readme_task, npmignore_task, tree_task)

    if not valid_dep_paths:
        no_dep_content.append(full_name)
        return

    # 4. Równoległe pobranie wszystkich znalezionych plików konfiguracyjnych
    dep_tasks = [fetch_raw_file(client, full_name, branch, path) for path in valid_dep_paths]
    dep_contents = await asyncio.gather(*dep_tasks)

    # 5. Agregacja i weryfikacja (logika dla JS)
    aggregated_deps = set()

    if lang == "JavaScript":
        if npm_file:
            print(f"- {full_name}: Discarded, has .npmignore")
            bad_dep_content.append(full_name)
            return

        for content, path in zip(dep_contents, valid_dep_paths):
            # if not content:
            #     continue

            try:
                pkg = json.loads(content)

                if any(key in pkg for key in ["types", "typings", "exports", "module"]):
                    print(f"- {full_name}: Discarded probably a library")
                    bad_dep_content.append(full_name)
                    return

                deps = pkg.get("dependencies", {})
                devDeps = pkg.get("devDependencies", {})

                aggregated_deps.update(deps.keys())
                aggregated_deps.update(devDeps.keys())

            except json.JSONDecodeError:
                print(f"Error when parsing JSON for {full_name} in file {path}")
                continue

        if len(aggregated_deps) < 5:
            print(f"- {full_name}: Discarded, too few dependencies ({len(aggregated_deps)})")
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
            print(f"{full_name}: Verified and saved (Found {len(valid_dep_paths)} files, {len(aggregated_deps)} unique deps)")
        except Exception as e:
            print(f"DB error for {full_name}: {e}")


async def main():

    # db_conn = await init_db()

    limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)
    async with httpx.AsyncClient(limits=limits) as client:
        start_date = "2018-01-01"
        end_date = "2026-01-01"

        print(f"Looking for JavaScript repos from {start_date} to {end_date}...")
        repos = await search_repositories_by_date(client, "JavaScript", start_date, end_date)

        # print(f"Found {len(repos)} repos. Starting to download files...")


        # Tworzymy zadania do współbieżnego pobierania plików
        tasks = [process_repository(client, repo) for repo in repos]

        # Uruchamiamy zadania paczkami (np. po 10 naraz), aby nie obciążyć GitHuba
        chunk_size = 10
        for i in range(0, len(tasks), chunk_size):
            await asyncio.gather(*tasks[i:i + chunk_size])
            await asyncio.sleep(2)  # Krótki oddech dla serwerów GitHuba

        good_dep_content_sort = sorted(good_dep_content)
        bad_dep_content_sort = sorted(bad_dep_content)
        no_dep_content_sort = sorted(no_dep_content)

        print(f"good repos: {len(good_dep_content)}")
        print(f"bad repos: {len(bad_dep_content)}")
        print(f"no content repos: {len(no_dep_content)}")

        with open("repos_results attempt3 5.txt", "a") as f:
            f.write(f"good repos: {len(good_dep_content_sort)}\n\n")
            for repo in good_dep_content_sort:
                f.write(f"{repo}\n")
            f.write("\nFP:")
            f.write(f"\n\nbad repos: {len(bad_dep_content_sort)}\n\n")
            for repo in bad_dep_content_sort:
                f.write(f"{repo}\n")
            f.write("\nFN:")
            f.write(f"\n\nno content repos: {len(no_dep_content_sort)}\n\n")
            for repo in no_dep_content_sort:
                f.write(f"{repo}\n")
            f.write("\nFN:")


if __name__ == "__main__":
    no_dep_content = []
    bad_dep_content = []
    good_dep_content = []

    asyncio.run(main())