from typing import Set

# TODO: 这个模块的功能是从简历文本中提取技能关键词，目前实现非常简单，后续可以考虑用更复杂的 NLP 模型来做（比如基于 LLM 的信息抽取）
KNOWN_SKILLS: Set[str] = {
    "react", "next.js", "nextjs", "node.js", "node", "typescript",
    "python", "pytorch", "tensorflow", "solidity", "web3", "rust",
    "docker", "kubernetes", "aws", "gcp"
}

def extract_skills_from_resume(resume_text: str) -> Set[str]:
    """
    从简历文本中提取技能关键词，目前实现非常简单，就是在文本中查找已知技能列表中的词
    后续可以考虑用更复杂的 NLP 模型来做（比如基于 LLM 的信息抽取）
    """
    resume_text = resume_text.lower()
    found = set()
    for skill in KNOWN_SKILLS:
        if skill in resume_text:
            found.add(skill)
    return found