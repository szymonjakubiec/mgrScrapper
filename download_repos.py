import os

from github import Github
import time
import psycopg2
from tqdm import tqdm
from dotenv import load_dotenv

from data_cleaning import clean_readme
from embedding import get_embedding

load_dotenv()
gh_token = os.getenv("GITHUB_TOKEN")
gh = Github(gh_token)

def get_readme(repo_name):
    try:
        # valid_files = ['requirements.txt', 'pyproject.toml', 'setup.py', 'package.json']

        repo = gh.get_repo(repo_name)
        readme = repo.get_readme().decoded_content.decode('utf-8')
        return readme
    except:
        return None




repos = gh.search_repositories(query="language:python, stars:>100", sort="stars", order="desc")

data = []
for repo in tqdm(repos[:30], desc="Downloading repos"):
    data.append(repo.full_name)
    # readme = get_readme(repo.full_name)
    # if readme:
    #     data.append({"name": repo.full_name, "readme": readme})

    time.sleep(1)
print('Finished downloading repos\n')

for name in data:
    print(name)

# conn = psycopg2.connect("host=localhost dbname=vector-db user=postgres password=ZAQ!2wsx")
# cursor = conn.cursor()
#
# for item in tqdm(data, desc="Embedding and saving repos to DB"):
#     clean_text = clean_readme(item['readme'])
#     vector = get_embedding(clean_text)
#
#     cursor.execute("INSERT INTO miniLM_embeddings (repo_name, description, embedding) VALUES (%s, %s, %s)",
#         (item['name'], clean_text[:500], vector))
#
# conn.commit()
# cursor.close()
# conn.close()