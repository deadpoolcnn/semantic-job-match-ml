"""
确保 NLTK 数据在应用启动前已下载
在任何使用 pyresparser 的模块之前导入此模块
"""
import nltk

def ensure_nltk_data():
    """下载所有必需的 NLTK 数据包"""
    packages = [
        ('corpora', 'stopwords'),
        ('tokenizers', 'punkt'),
        ('taggers', 'averaged_perceptron_tagger'),
        ('chunkers', 'maxent_ne_chunker'),
        ('corpora', 'words'),
        ('corpora', 'wordnet'),
        ('corpora', 'omw-1.4'),
    ]
    
    missing = []
    for subdir, package in packages:
        try:
            nltk.data.find(f'{subdir}/{package}')
        except LookupError:
            missing.append(package)
    
    if missing:
        print(f"⚠️  Downloading {len(missing)} missing NLTK packages...")
        for package in missing:
            print(f"  - {package}")
            nltk.download(package, quiet=True)
        print("✅ NLTK data download complete")
    
    return True

# 模块加载时自动执行
ensure_nltk_data()
