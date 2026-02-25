"""
职位匹配配置：职级层级和技术栈生态系统定义
"""

from typing import Dict, Set
# ============================================
# 职级层级定义（从低到高：0-8）
# ============================================

SENIORITY_HIERARCHY: Dict[str, int] = {
    # ===== 实习生/新人层级 (Level 0) =====
    "intern": 0,
    "internship": 0,
    "trainee": 0,
    "apprentice": 0,
    "graduate": 0,
    
    # ===== 初级层级 (Level 1) =====
    "junior": 1,
    "junior developer": 1,
    "junior engineer": 1,
    "junior software engineer": 1,
    "associate": 1,
    "associate engineer": 1,
    "entry level": 1,
    "entry-level": 1,
    "jr": 1,
    "jr.": 1,
    
    # ===== 中级层级 (Level 2) =====
    "mid": 2,
    "mid-level": 2,
    "mid level": 2,
    "intermediate": 2,
    "developer": 2,           # 无前缀的 developer 视为中级
    "engineer": 2,            # 无前缀的 engineer 视为中级
    "software engineer": 2,
    "software developer": 2,
    "developer ii": 2,
    "engineer ii": 2,
    "sde ii": 2,
    
    # ===== 高级层级 (Level 3) =====
    "senior": 3,
    "senior developer": 3,
    "senior engineer": 3,
    "senior software engineer": 3,
    "senior software developer": 3,
    "sr": 3,
    "sr.": 3,
    "developer iii": 3,
    "engineer iii": 3,
    "sde iii": 3,
    
    # ===== 专家/主管层级 (Level 4) =====
    "lead": 4,
    "tech lead": 4,
    "technical lead": 4,
    "lead engineer": 4,
    "lead developer": 4,
    "staff": 4,
    "staff engineer": 4,
    "staff software engineer": 4,
    "principal": 4,
    "principal engineer": 4,
    "principal software engineer": 4,
    "architect": 4,
    "senior staff engineer": 4,
    
    # ===== 管理层级 (Level 5) =====
    "manager": 5,
    "engineering manager": 5,
    "development manager": 5,
    "team lead": 5,
    "team leader": 5,
    "tech manager": 5,
    "technical manager": 5,
    
    # ===== 高级管理层级 (Level 6) =====
    "senior manager": 6,
    "senior engineering manager": 6,
    "director": 6,
    "director of engineering": 6,
    "senior director": 6,
    "head of engineering": 6,
    "group manager": 6,
    
    # ===== 执行层级 (Level 7) =====
    "vp": 7,
    "vice president": 7,
    "vp of engineering": 7,
    "svp": 7,
    "senior vice president": 7,
    "senior vp": 7,
    "avp": 7,
    "assistant vice president": 7,
    
    # ===== C级高管 (Level 8) =====
    "cto": 8,
    "chief technology officer": 8,
    "ceo": 8,
    "chief executive officer": 8,
    "cfo": 8,
    "chief financial officer": 8,
    "coo": 8,
    "chief operating officer": 8,
    "cio": 8,
    "chief information officer": 8,
    "c-level": 8,
    "c level": 8,
    "executive": 8,
}

# ============================================
# 年限
# ============================================
YEARS_TO_LEVEL = {
        (0, 1):   1,   # Junior
        (1, 3):   2,   # Mid
        (3, 6):   3,   # Senior
        (6, 10):  4,   # Staff/Lead
        (10, 15): 5,   # Manager
        (15, 99): 6,   # Director+
    }

# ============================================
# 技术栈生态系统定义
# ============================================
TECH_ECOSYSTEMS: Dict[str, Set[str]] = {
    # ===== 前端框架生态 =====
    "frontend_framework": {
        "react", "react.js", "reactjs",
        "next.js", "nextjs", "next",
        "vue", "vue.js", "vuejs",
        "nuxt", "nuxt.js", "nuxtjs",
        "angular", "angularjs", "angular.js",
        "svelte", "sveltekit",
        "solid", "solidjs",
        "qwik",
    },
    
    # ===== 前端状态管理 =====
    "frontend_state": {
        "redux", "redux toolkit",
        "mobx", "mobx-state-tree",
        "zustand",
        "recoil",
        "jotai",
        "valtio",
        "pinia",  # Vue
        "vuex",   # Vue
    },
    
    # ===== CSS 框架/预处理器 =====
    "css_framework": {
        "tailwind", "tailwind css", "tailwindcss",
        "bootstrap",
        "material ui", "mui", "material-ui",
        "ant design", "antd",
        "chakra ui", "chakra-ui",
        "bulma",
        "foundation",
        "sass", "scss",
        "less",
        "styled-components",
        "emotion",
        "css modules",
    },
    
    # ===== 前端构建工具 =====
    "frontend_tooling": {
        "webpack",
        "vite",
        "rollup",
        "parcel",
        "esbuild",
        "turbopack",
        "babel",
        "swc",
        "typescript", "ts",
        "eslint",
        "prettier",
    },
    
    # ===== 后端 Python 生态 =====
    "backend_python": {
        "python",
        "django",
        "flask",
        "fastapi",
        "pyramid",
        "tornado",
        "bottle",
        "cherrypy",
        "aiohttp",
        "sanic",
    },
    
    # ===== 后端 JavaScript/TypeScript 生态 =====
    "backend_js": {
        "node.js", "nodejs", "node",
        "javascript", "js",
        "typescript", "ts",
        "express", "express.js",
        "nestjs", "nest.js", "nest",
        "koa", "koa.js",
        "hapi", "hapi.js",
        "fastify",
        "adonis", "adonisjs",
    },
    
    # ===== 后端 Java 生态 =====
    "backend_java": {
        "java",
        "spring", "spring boot", "springboot",
        "spring framework",
        "hibernate",
        "maven",
        "gradle",
        "jakarta ee", "java ee",
        "micronaut",
        "quarkus",
    },
    
    # ===== 后端 Go 生态 =====
    "backend_go": {
        "go", "golang",
        "gin",
        "echo",
        "fiber",
        "beego",
        "chi",
    },
    
    # ===== 后端 C# 生态 =====
    "backend_csharp": {
        "c#", "csharp",
        ".net", "dotnet", ".net core",
        "asp.net", "asp.net core",
        "entity framework",
    },
    
    # ===== 后端 Ruby 生态 =====
    "backend_ruby": {
        "ruby",
        "ruby on rails", "rails",
        "sinatra",
    },
    
    # ===== 后端 PHP 生态 =====
    "backend_php": {
        "php",
        "laravel",
        "symfony",
        "codeigniter",
        "wordpress",
    },
    
    # ===== 后端 Rust 生态 =====
    "backend_rust": {
        "rust",
        "actix", "actix-web",
        "rocket",
        "axum",
        "warp",
    },
    
    # ===== 移动端生态 =====
    "mobile_ios": {
        "ios",
        "swift",
        "objective-c",
        "swiftui",
        "uikit",
        "xcode",
    },
    
    "mobile_android": {
        "android",
        "kotlin",
        "java",
        "jetpack compose",
        "android studio",
    },
    
    "mobile_crossplatform": {
        "react native",
        "flutter",
        "dart",
        "ionic",
        "cordova",
        "xamarin",
    },
    
    # ===== 数据库生态 =====
    "database_sql": {
        "sql",
        "postgresql", "postgres",
        "mysql",
        "mariadb",
        "sql server", "mssql",
        "oracle", "oracle db",
        "sqlite",
    },
    
    "database_nosql": {
        "mongodb", "mongo",
        "redis",
        "elasticsearch", "elastic",
        "cassandra",
        "dynamodb",
        "couchdb",
        "neo4j",
        "influxdb",
    },
    
    # ===== 消息队列/流处理 =====
    "message_queue": {
        "kafka", "apache kafka",
        "rabbitmq",
        "redis",
        "aws sqs",
        "google pub/sub", "pubsub",
        "activemq",
        "nats",
        "pulsar",
    },
    
    # ===== DevOps/云计算 =====
    "cloud_aws": {
        "aws", "amazon web services",
        "ec2", "s3", "lambda", "rds",
        "cloudformation",
        "eks", "ecs",
    },
    
    "cloud_azure": {
        "azure", "microsoft azure",
        "azure functions",
        "azure devops",
        "aks",
    },
    
    "cloud_gcp": {
        "gcp", "google cloud", "google cloud platform",
        "compute engine",
        "cloud functions",
        "gke",
    },
    
    "devops_containers": {
        "docker",
        "kubernetes", "k8s",
        "containerd",
        "podman",
        "helm",
    },
    
    "devops_iac": {
        "terraform",
        "ansible",
        "cloudformation",
        "pulumi",
        "chef",
        "puppet",
    },
    
    "devops_cicd": {
        "jenkins",
        "gitlab ci", "gitlab-ci",
        "github actions",
        "circleci",
        "travis ci",
        "azure devops",
        "teamcity",
        "bamboo",
    },
    
    # ===== 测试框架 =====
    "testing_frontend": {
        "jest",
        "mocha",
        "chai",
        "jasmine",
        "cypress",
        "playwright",
        "selenium",
        "webdriver",
        "testing library", "react testing library",
    },
    
    "testing_backend": {
        "pytest",
        "unittest",
        "junit", "junit5",
        "testng",
        "mocha",
        "jest",
        "rspec",
        "phpunit",
    },
    
    # ===== API 技术 =====
    "api_tech": {
        "rest", "rest api", "restful",
        "graphql",
        "grpc",
        "websocket",
        "soap",
        "openapi", "swagger",
    },
    
    # ===== 数据工程/机器学习 =====
    "data_engineering": {
        "spark", "apache spark",
        "hadoop",
        "airflow", "apache airflow",
        "flink",
        "databricks",
        "snowflake",
        "dbt",
    },
    
    "machine_learning": {
        "tensorflow",
        "pytorch",
        "scikit-learn", "sklearn",
        "keras",
        "pandas",
        "numpy",
        "jupyter",
        "mlflow",
    },
    
    # ===== 区块链/Web3 =====
    "blockchain": {
        "blockchain",
        "ethereum",
        "solidity",
        "web3", "web3.js",
        "smart contract",
        "bitcoin",
        "hyperledger",
    },
}

# 技能间显式关系：(skill_a, skill_b, weight)
SKILL_RELATIONS = [
    # ML 框架
    ("pytorch",      "tensorflow",    0.7),
    ("pytorch",      "keras",         0.8),
    ("tensorflow",   "keras",         0.9),
    ("scikit-learn", "pandas",        0.9),
    ("scikit-learn", "numpy",         0.9),
    ("pandas",       "numpy",         0.95),
    ("mlflow",       "pytorch",       0.6),
    ("mlflow",       "tensorflow",    0.6),

    # 前端框架
    ("react",        "next.js",       0.9),
    ("vue",          "nuxt",          0.9),
    ("react",        "vue",           0.6),
    ("angular",      "typescript",    0.9),
    ("react",        "typescript",    0.8),
    ("redux",        "react",         0.85),
    ("zustand",      "react",         0.8),

    # 后端
    ("fastapi",      "python",        0.95),
    ("django",       "python",        0.95),
    ("flask",        "python",        0.95),
    ("spring boot",  "java",          0.95),
    ("node.js",      "javascript",    0.95),
    ("nestjs",       "node.js",       0.9),
    ("express",      "node.js",       0.85),

    # 数据库
    ("postgresql",   "sql",           0.9),
    ("mysql",        "sql",           0.9),
    ("mongodb",      "nosql",         0.85),
    ("redis",        "cache",         0.9),
    ("elasticsearch","search",        0.9),

    # DevOps
    ("kubernetes",   "docker",        0.9),
    ("helm",         "kubernetes",    0.85),
    ("terraform",    "aws",           0.7),
    ("terraform",    "gcp",           0.7),
    ("terraform",    "azure",         0.7),
    ("github actions","ci/cd",        0.85),
    ("jenkins",      "ci/cd",         0.85),

    # 语言互通
    ("javascript",   "typescript",    0.85),
    ("python",       "data science",  0.75),
    ("rust",         "systems programming", 0.9),
    ("go",           "microservices", 0.7),
]

# ============================================
# 职级匹配权重配置
# ============================================

SENIORITY_MATCH_SCORES: Dict[int, float] = {
    0: 1.0,    # 完全匹配
    1: 0.85,   # 降级 1 级
    -1: 0.90,  # 晋升 1 级
    2: 0.60,   # 降级 2 级
    -2: 0.50,  # 晋升 2 级
    3: 0.30,   # 降级 3+ 级
    -3: 0.20,  # 晋升 3+ 级
}

# ============================================
# 综合评分权重配置
# ============================================

SCORING_WEIGHTS = {
    "semantic": 0.30,      # 语义相似度
    "skill": 0.50,         # 技能匹配度
    "seniority": 0.10,     # 职级匹配度
    "tech_stack": 0.10,    # 技术栈匹配度
}

# ============================================
# 五维评分权重
# ============================================

FIVE_DIM_WEIGHTS = {
    "semantic": 0.30,      # 语义匹配
    "skill_graph": 0.25,   # 技能图谱匹配
    "seniority": 0.20,     # 职级匹配
    "culture": 0.15,       # 文化/价值观匹配
    "salary": 0.10,        # 薪资匹配
}

# ============================================
# 文化维度关键词词典
# ============================================
CULTURE_DIMENSIONS: Dict[str, list[str]] = {
    "work_life_balance": [
        "work-life balance", "flexible hours", "remote work", "async",
        "no crunch", "sustainable pace", "family friendly",
    ],
    "fast_paced": [
        "fast-paced", "high-growth", "startup", "move fast", "agile",
        "rapid iteration", "ship fast", "hustle",
    ],
    "innovation": [
        "innovation", "cutting-edge", "r&d", "research", "experimental",
        "creative", "new technology", "pioneering",
    ],
    "collaboration": [
        "collaborative", "team player", "cross-functional", "open communication",
        "pair programming", "mentorship", "knowledge sharing",
    ],
    "autonomy": [
        "autonomous", "self-directed", "ownership", "independent",
        "empowered", "flat hierarchy", "no micromanagement",
    ],
    "data_driven": [
        "data-driven", "metrics", "kpi", "analytics", "evidence-based",
        "a/b testing", "experimentation",
    ],
    "diversity_inclusion": [
        "diversity", "inclusion", "equity", "dei", "belonging",
        "inclusive", "equal opportunity",
    ],
    "learning_growth": [
        "learning", "growth", "career development", "training budget",
        "conference", "upskilling", "mentorship", "promotion",
    ],
}

# ============================================
# 文化维度标准Prompt（用于 Embedding）
# ============================================
DIMENSION_ANCHORS: dict[str, str] = {
    "work_life_balance": "work life balance flexible schedule remote work",
    "fast_paced":        "fast paced startup environment rapid growth hustle",
    "innovation":        "innovation cutting edge technology research development",
    "collaboration":     "team collaboration cross functional communication",
    "autonomy":          "autonomy ownership independent decision making",
    "data_driven":       "data driven analytics metrics evidence based decisions",
    "diversity_inclusion": "diversity inclusion equity belonging culture",
    "learning_growth":   "learning growth career development training mentorship",
}

# ============================================
# 货币汇率归一化
# ============================================
CURRENCY_TO_USD: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.27,
    "CNY": 0.14,
    "JPY": 0.0067,
    "CAD": 0.74,
    "AUD": 0.65,
    "SGD": 0.75,
    "INR": 0.012,
}

# ============================================
# 薪资周期归一化
# ============================================
PERIOD_MULTIPLIER: dict[str, float] = {
    "annual":  1.0,
    "monthly": 12.0,
    "hourly":  2080.0,  # 52周 * 40小时
    "daily":   260.0,   # 52周 * 5天
}

# ============================================
# 辅助函数
# ============================================
def get_seniority_keywords() -> list[str]:
    """获取所有职级关键词（按长度降序）"""
    return sorted(SENIORITY_HIERARCHY.keys(), key=len, reverse=True)

def get_tech_ecosystem_names() -> list[str]:
    """获取所有技术生态系统名称"""
    return list(TECH_ECOSYSTEMS.keys())

def add_custom_skill(ecosystem: str, skill: str) -> None:
    """
    添加自定义技能到指定生态系统
    
    Args:
        ecosystem: 生态系统名称
        skill: 技能名称（会自动转为小写）
    """
    if ecosystem not in TECH_ECOSYSTEMS:
        raise ValueError(f"Unknown ecosystem: {ecosystem}")
    TECH_ECOSYSTEMS[ecosystem].add(skill.lower())

def add_custom_seniority(keyword: str, level: int) -> None:
    """
    添加自定义职级关键词
    
    Args:
        keyword: 职级关键词（会自动转为小写）
        level: 职级层级 (0-8)
    """
    if not 0 <= level <= 8:
        raise ValueError(f"Seniority level must be between 0 and 8, got {level}")
    SENIORITY_HIERARCHY[keyword.lower()] = level

# ============================================
# 示例：如何添加自定义配置
# ============================================

if __name__ == "__main__":
    # 添加自定义技能
    add_custom_skill("frontend_framework", "htmx")
    add_custom_skill("backend_python", "litestar")
    
    # 添加自定义职级
    add_custom_seniority("senior staff", 4)
    add_custom_seniority("distinguished engineer", 5)
    
    print(f"Total seniority keywords: {len(SENIORITY_HIERARCHY)}")
    print(f"Total tech ecosystems: {len(TECH_ECOSYSTEMS)}")
    print(f"Example ecosystem (frontend_framework): {TECH_ECOSYSTEMS['frontend_framework']}")