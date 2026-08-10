import asyncio
import random
import httpx
import asyncpg
import datetime
import json
import os
from dotenv import load_dotenv
import re
import argparse


load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

curr_dir = os.path.dirname(__file__)
postgres_env_path = os.path.join(curr_dir, "docker-compose\\postgres_db", ".env")
load_dotenv(dotenv_path=postgres_env_path)
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB = os.getenv("POSTGRES_DB")
DB_PORT = os.getenv("DB_PORT")

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


parser = argparse.ArgumentParser(description="Loading repos from GitHub")
parser.add_argument("--db_table_name", type=str, default="default_table", help="Nazwa tabeli w bazie")
parser.add_argument("--start_date", type=str, required=True, help="Start date (YYYY-MM-DD)")
parser.add_argument("--end_date", type=str, required=True, help="End date (YYYY-MM-DD)")
parser.add_argument("--min_stars", type=int, default=10, help="Minimal number of stars")

args = parser.parse_args()

DB_TABLE_NAME = args.db_table_name
START_DATE = args.start_date
END_DATE = args.end_date
MIN_STARS = args.min_stars


async def init_db():
    """Creates a pool of max 20 connections to DB in Docker."""

    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@localhost:{DB_PORT}/{POSTGRES_DB}"
    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=20)

    async with pool.acquire() as conn:
        await conn.execute(f'''
                           CREATE TABLE IF NOT EXISTS {DB_TABLE_NAME}
                           (
                               id              SERIAL  NOT NULL PRIMARY KEY,
                               name            TEXT UNIQUE NOT NULL,
                               "desc"          TEXT,
                               deps            TEXT[],
                               raw_desc        TEXT,
                               deps_devdeps    TEXT[]
                           )
                           ''')
    return pool


async def fetch_raw_file(client, full_name, default_branch, file_path):
    """
    Downloads file while avoiding API limitations, using raw.githubusercontent.com
    """
    url = f"https://raw.githubusercontent.com/{full_name}/{default_branch}/{file_path}"
    for attempt in range(3):
        try:
            response = await client.get(url, headers=HEADERS, timeout=10.0)
            if response.status_code == 200:
                return response.text

            elif response.status_code in (403,429):
                # Random jitter 0.1 - 1.5 seconds
                retry_after = int(response.headers.get("retry-after", 0))
                if retry_after > 0:
                    sleep_time = retry_after + random.uniform(0.1, 1.5)
                else:
                    # Exponential backoff: 2s, 4s, 8s + jitter
                    sleep_time = (2 ** attempt) + random.uniform(0.1, 1.5)
                print(f"[RAW API] Reached limit for raw  {file_path} in {full_name}. Waiting {sleep_time:.2f}s (Attempt {attempt + 1}/3)...")
                await asyncio.sleep(sleep_time)
                continue  # Spróbuj ponownie

            else:
                return None
        except Exception as e:
            print(f"[RAW API] Network Error for {file_path} in {full_name}: {e}. (Attempt {attempt + 1}/3)")
            sleep_time = (2 ** attempt) + random.uniform(0.1, 1.0)
            await asyncio.sleep(sleep_time)
    print(f"[RAW API] Giving up for {file_path} in {full_name} after 3 attempts.")
    return None

async def fetch_repo_tree_paths(client, full_name, default_branch, dep_filename):
    """
    Fetches the full repository file tree via the GitHub API.
    Rejects the repo if it contains an .npmignore in the root directory.
    Also returns the name of the readme file.
    """

    url = f"https://api.github.com/repos/{full_name}/git/trees/{default_branch}?recursive=1" # ?recursive=1 fetches whole tree with 1 query
    readme_file = ""
    for attempt in range(3):
        try:
            response = await client.get(url, headers=HEADERS, timeout=10.0)

            if response.status_code == 200:
                data = response.json()
                paths = []
                for item in data.get("tree", []):
                    # only looking for blob files
                    if item.get("type") == "blob":
                        path = item["path"]

                        if re.match(r"readme(\.[a-z]+)?", path.lower()): # readme file with any extension
                            readme_file = path

                        if path.lower() == ".npmignore":
                            # print(f"- {full_name}: Discarded, has .npmignore")
                            return [], "discarded-npmignore", ""

                        if not path.endswith(dep_filename):
                            continue

                        parts = path.split('/')
                        depth = len(parts) - 1

                        if depth > 2:
                            continue

                        if any(part.startswith('.') for part in parts):
                            continue

                        paths.append(path)

                return paths, "OK", readme_file

            elif response.status_code in (403, 429):
                reset_timestamp = int(response.headers.get("X-RateLimit-Reset", 0))
                current_timestamp = int(datetime.datetime.now().timestamp())

                retry_after = int(response.headers.get("Retry-After", 0))
                sleep_time = retry_after if retry_after else max(reset_timestamp - current_timestamp, 60)

                print(f"[GITHUB API] Reached limit for {full_name}, waiting {sleep_time} seconds (attempt #{attempt+1}/3)...")
                await asyncio.sleep(sleep_time)
                continue

            else:
                print(f"[GITHUB API] Error {response.status_code} while downloading tree: {full_name}")
                return [], "Error", ""

        except Exception as e:
            print(f"[GITHUB API] Exception while downloading tree {full_name}: {e}")
            return [], "Exception", ""
    return [], "Limit", ""



async def search_repositories_by_date(client, language, start_date, end_date):
    """
    Searches repositories in specified time frame, to avoid 1000 results limit.
    """

    exclusions = " ".join([f"-topic:{topic}" for topic in EXCLUDED_TOPICS])
    query = f"language:{language} stars:>{MIN_STARS} {exclusions} created:{start_date}..{end_date}"

    url = "https://api.github.com/search/repositories"

    repos = []
    page = 1
    max_pages = 10

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

            elif response.status_code in (403, 429):
                reset_timestamp = int(response.headers.get("X-RateLimit-Reset", 0))
                current_timestamp = int(datetime.datetime.now().timestamp())
                retry_after = int(response.headers.get("Retry-After", 0))

                sleep_time = retry_after if retry_after else max(reset_timestamp - current_timestamp, 60)
                print(f"[GITHUB API] Reached limit, waiting {sleep_time} seconds to restart...")
                await asyncio.sleep(sleep_time + 2)
                continue
            else:
                print(f"[GITHUB API] API error {response.status_code}: {response.text}")
                break

        except Exception as e:
            print(f"[GITHUB API] Searching error: {e}")
            # Waiting a bit in case of network error before the next attempt
            await asyncio.sleep(10)

    return repos

async def process_repository(client, repo, db_pool):
    """Fetches README and dependency files, then saves them to DB."""
    full_name = repo["full_name"]
    branch = repo["default_branch"]
    lang = repo["language"]

    if any(word in full_name.lower() for word in EXCLUDED_TITLEWORDS):
        # print(f"- {full_name}: Discarded, keyword match in name (tutorial/book)")
        bad_dep_content.append(full_name)
        return

    if lang == "JavaScript":
        dep_filename = "package.json"
    else:
        print(f"- Language {lang} is not yet supported")
        return

    valid_dep_paths, status, readme_file = await fetch_repo_tree_paths(client, full_name, branch, dep_filename)

    if status == "discarded-npmignore":
        bad_dep_content.append(full_name)
        return

    if status in ["Limit", "Error", "Exception"] or not valid_dep_paths:
        no_dep_content.append(full_name)
        return

    if not readme_file:
        no_dep_content.append(full_name)
        return

    # fetch README and all package.json files in parallel
    tasks = [fetch_raw_file(client, full_name, branch, readme_file)]
    for path in valid_dep_paths:
        tasks.append(fetch_raw_file(client, full_name, branch, path))

    results = await asyncio.gather(*tasks)

    readme_content = results[0]
    dep_contents = results[1:]


    aggregated_deps = set()
    aggregated_deps_devdeps = set()

    if lang == "JavaScript":

        for content, path in zip(dep_contents, valid_dep_paths):
            if not content:
                continue

            try:
                pkg = json.loads(content)

                if not isinstance(pkg, dict):
                    print(f"Format Error for {full_name}: {path} is not JSON object.")
                    continue

                if any(key in pkg for key in ["types", "typings", "exports", "module"]):
                    # print(f"- {full_name}: Discarded probably a library")
                    bad_dep_content.append(full_name)
                    return

                deps = pkg.get("dependencies", {})
                devDeps = pkg.get("devDependencies", {})

                aggregated_deps.update(deps.keys())

                aggregated_deps_devdeps.update(deps.keys())
                aggregated_deps_devdeps.update(devDeps.keys())

            except json.JSONDecodeError:
                print(f"Error when parsing JSON for {full_name} in file {path}")
                continue
            except Exception as e:
                print(f"Other Error within {full_name} in file {path}: {e}")

        if len(aggregated_deps_devdeps) < 5:
            # print(f"- {full_name}: Discarded, too few dependencies ({len(aggregated_deps_devdeps)})")
            bad_dep_content.append(full_name)
            return

        try:
            deps_devdeps_list = list(aggregated_deps_devdeps)
            deps_list = list(aggregated_deps)
            safe_readme = readme_content.replace('\x00', '') if readme_content else ""

            good_dep_content.append(full_name)
            async with db_pool.acquire() as conn:
                await conn.execute(f'''
                                       INSERT INTO {DB_TABLE_NAME} (name, deps, raw_desc, deps_devdeps)
                                       VALUES ($1, $2, $3, $4)
                                       ON CONFLICT (name) DO NOTHING
                                       ''', full_name, deps_list, safe_readme, deps_devdeps_list)

            # print(f"{full_name}: Verified and saved (Found {len(valid_dep_paths)} files, {len(aggregated_deps_devdeps)} unique deps)")
        except Exception as e:
            print(f"DB error for {full_name}: {e}")


async def main():

    db_pool = await init_db()

    limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)
    async with httpx.AsyncClient(limits=limits) as client:
        current_start_date = datetime.datetime.strptime(START_DATE, "%Y-%m-%d")
        final_end_date = datetime.datetime.strptime(END_DATE, "%Y-%m-%d")
        step = datetime.timedelta(days=30)

        while current_start_date < final_end_date:
            current_end_date = current_start_date + step
            if current_end_date > final_end_date:
                current_end_date = final_end_date

            start_str = current_start_date.strftime("%Y-%m-%d")
            end_str = current_end_date.strftime("%Y-%m-%d")

            print(f"\n==================================================")
            print(f"STARTING WINDOW: {start_str} .. {end_str}")
            print(f"==================================================\n")


            print(f"Looking for JavaScript repos from {current_start_date} to {current_end_date}...")
            repos = await search_repositories_by_date(client, "JavaScript", start_str, end_str)

            if repos:
                print("Processing repositories...")
                tasks = [process_repository(client, repo, db_pool) for repo in repos]

                chunk_size = 10
                for i in range(0, len(tasks), chunk_size):
                    await asyncio.gather(*tasks[i:i + chunk_size])
                    await asyncio.sleep(2)
            else:
                print(f"No repositories within window of {start_str} to {end_str}.")

            with open("repos_results_log.txt", "a", encoding="utf-8") as f:
                f.write(f"SUMMARY FOR WINDOW: {start_str} .. {end_str}\n")
                f.write(f"Saved: {len(good_dep_content)} repos\n")
                f.write(f"Discarded (Bad): {len(bad_dep_content)} repos\n")
                f.write(f"Discarded (No Content): {len(no_dep_content)} repos\n")

            good_dep_content.clear()
            bad_dep_content.clear()
            no_dep_content.clear()
            current_start_date = current_end_date + datetime.timedelta(days=1)

            await asyncio.sleep(3)

        await db_pool.close()
        print(f"\n SUCCESSFULLY FINISHED DOWNLOADING THE WHOLE PERIOD {START_DATE}-{END_DATE}!")

            # good_dep_content_sort = sorted(good_dep_content, key=str.lower)
            # bad_dep_content_sort = sorted(bad_dep_content, key=str.lower)
            # no_dep_content_sort = sorted(no_dep_content, key=str.lower)
            #
            # print(f"good repos: {len(good_dep_content)}")
            # print(f"bad repos: {len(bad_dep_content)}")
            # print(f"no content repos: {len(no_dep_content)}")
            #
            # with open("repos_results attempt5 2.txt", "a") as f:
            #     f.write(f"good repos: {len(good_dep_content_sort)}\n\n")
            #     for repo in good_dep_content_sort:
            #         f.write(f"{repo}\n")
            #     f.write("\nFP:")
            #     f.write(f"\n\nbad repos: {len(bad_dep_content_sort)}\n\n")
            #     for repo in bad_dep_content_sort:
            #         f.write(f"{repo}\n")
            #     f.write("\nFN:")
            #     f.write(f"\n\nno content repos: {len(no_dep_content_sort)}\n\n")
            #     for repo in no_dep_content_sort:
            #         f.write(f"{repo}\n")
            #     f.write("\nFN:")


if __name__ == "__main__":
    no_dep_content = []
    bad_dep_content = []
    good_dep_content = []

    asyncio.run(main())