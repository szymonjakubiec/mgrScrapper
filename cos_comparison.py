import psycopg2

from embedding import get_embedding

def get_similar_projects(query_text, limit=5):
    print("Looking for similar projects...")

    query_vector = get_embedding(query_text)
    query_vector_str = str(query_vector)

    conn = psycopg2.connect("host=localhost dbname=vector-db user=postgres password=ZAQ!2wsx")
    cursor = conn.cursor()

    sql = """
        SELECT
            repo_name,
            description,
            1 - (embedding <=> %s::vector) AS cos_similarity
        FROM miniLM_embeddings
        ORDER BY cos_similarity DESC
        LIMIT %s;
    """

    cursor.execute(sql, (query_vector_str, limit))
    results = cursor.fetchall()

    cursor.close()
    conn.close()

    return results

if __name__ == '__main__':
    query_text = "A lightweight framework for building fast web APIs in Python using async and await."

    similar_projects = get_similar_projects(query_text)

    print("FOUND THESE PROJECTS:")
    print("-" * 50)
    for row in similar_projects:
        repo_name = row[0]
        description = row[1]
        similarity = row[2]

        print(f"[{similarity * 100:.2f}%] Repo: {repo_name}")
        print(f"Desc: {description}")
        print("-" * 50)