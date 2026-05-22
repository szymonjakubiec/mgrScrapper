import psycopg2
from mgrScrapper.embedding import get_embedding


def get_similar_projects(query_text, model_name="all-MiniLM-L6-v2", limit=5):
    print(f"Szukanie projektów podobnych do: '{query_text}'...")

    query_vector = get_embedding(query_text)

    query_vector_str = str(query_vector)

    db_params = "host=localhost dbname=vector-db user=postgres password=ZAQ!2wsx port=5433"

    try:
        # 2. Otwarcie połączenia z użyciem bloku 'with' (bezpieczne zamykanie)
        with psycopg2.connect(db_params) as conn:
            with conn.cursor() as cursor:
                sql = """
                      SELECT r.name, \
                             r.short_desc, \
                             r.dependencies, \
                             1 - (e.embedding <=> %s::vector) AS cos_similarity
                      FROM embeddings e
                               JOIN repo r ON e.repo_id = r.id
                      WHERE e.model_name = %s
                      ORDER BY cos_similarity DESC
                      LIMIT %s; \
                      """

                cursor.execute(sql, (query_vector_str, model_name, limit))
                results = cursor.fetchall()

                return results

    except psycopg2.Error as e:
        print(f"Wystąpił błąd podczas operacji na bazie danych: {e}")
        return []


if __name__ == '__main__':
    query_text = "A lightweight framework for building fast web APIs in Python using async and await."

    similar_projects = get_similar_projects(query_text)

    print("\nZNALEZIONO NASTĘPUJĄCE PROJEKTY:")
    print("-" * 70)

    for row in similar_projects:
        repo_name = row[0]
        description = row[1]
        dependencies = row[2]
        similarity = row[3]

        print(f"[{similarity * 100:.2f}%] Repo: {repo_name}")
        print(f"Opis: {description}")

        deps_formatted = ", ".join(dependencies) if dependencies else "Brak zidentyfikowanych zależności"
        print(f"Sugerowane zależności: {deps_formatted}")
        print("-" * 70)