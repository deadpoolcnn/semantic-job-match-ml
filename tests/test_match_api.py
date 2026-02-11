import json
from pathlib import Path

import requests

RootDir = Path(__file__).resolve().parents[1]
TEST_RESUMES_PATH = RootDir / "data" / "tests" / "test_resumes.json"

API_URL = "http://127.0.0.1:8000/api/match_resume"

def main():
    with open(TEST_RESUMES_PATH, "r", encoding="utf-8") as f:
        test_resumes = json.load(f)

    for idx, case in enumerate(test_resumes):
        rid = case["id"]
        text = case["text"]

        response = requests.post(
            API_URL, 
            json={"resume_text": text, "top_k": 3}
        )
        data = response.json()
        print("=" * 80)
        print(f"Resume ID: {rid}")
        print(f"Input: {text}\n")
        for i, match in enumerate(data["matches"], start=1):
            print(
                f"[{i}] {match['job_title']} @ {match['company']} | "
                f"score={match['score']:.3f}, "
                f"semantic={match.get('semantic_score', 0):.3f}, "
                f"overlap={match.get('skill_overlap', 0):.3f}"
            )
            print("  why_match:", "; ".join(match.get("why_match", [])))
            print("  skill_gaps:", "; ".join(match.get("skill_gaps", [])))
            print()

if __name__ == "__main__":
    main()