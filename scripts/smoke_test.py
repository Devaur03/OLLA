import urllib.request
import json

data = json.dumps({
    "query": "how does pgvector work for semantic search",
    "max_results": 3,
    "chunk_size": 400,
    "chunk_overlap": 40
}).encode()

req = urllib.request.Request(
    "http://localhost:8000/api/v1/search",
    data=data,
    headers={"Content-Type": "application/json"}
)

try:
    r = urllib.request.urlopen(req, timeout=60)
    resp = json.loads(r.read())
    print("query:", resp["query"])
    print("total_results:", resp["total_results"])
    print("processing_time_ms:", resp["processing_time_ms"])
    for res in resp["results"]:
        print(f"  rank={res['rank']} score={res['score']} chunks={res['chunk_count']} title={res['title'][:70]}")
except Exception as e:
    print("ERROR:", e)
