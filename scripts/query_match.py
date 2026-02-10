import requests
import json

url = "http://127.0.0.1:8000/api/match_resume"
data = {
    "resume_text": "React full-stack developer with Web3 experience, 3 years Next.js",
    "top_k": 1
}

response = requests.post(url, json=data)
# 打印响应结果
print(json.dumps(response.json(), indent=2, ensure_ascii=False))