from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
import os

load_dotenv()
# os.environ["HF_TOKEN"] = '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'
model = SentenceTransformer('all-MiniLM-L6-v2')

def get_embedding(readme_text):
    return model.encode(readme_text).tolist()

# sample_desc = "FastAPI framework, high performance, easy to learn"
# vector = get_embedding(sample_desc)
# print(vector)