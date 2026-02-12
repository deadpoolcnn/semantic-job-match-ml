"""
Download required NLTK data for resume parsing
"""
import nltk
import sys

# NLTK 数据包列表（pyresparser 需要）
REQUIRED_PACKAGES = [
    'stopwords',              # 停用词
    'punkt',                  # 分词器
    'averaged_perceptron_tagger',  # 词性标注
    'maxent_ne_chunker',      # 命名实体识别
    'words',                  # 单词列表
    'wordnet',                # 词网
    'omw-1.4',                # 开放多语言 WordNet
]

def download_nltk_data():
    """下载所有必需的 NLTK 数据包"""
    print("Downloading NLTK data packages...")
    print("=" * 60)
    
    success_count = 0
    failed_packages = []
    
    for package in REQUIRED_PACKAGES:
        try:
            print(f"Downloading '{package}'...", end=" ")
            nltk.download(package, quiet=True)
            print("✅ Done")
            success_count += 1
        except Exception as e:
            print(f"❌ Failed: {e}")
            failed_packages.append(package)
    
    print("=" * 60)
    print(f"Successfully downloaded: {success_count}/{len(REQUIRED_PACKAGES)} packages")
    
    if failed_packages:
        print(f"Failed packages: {', '.join(failed_packages)}")
        return 1
    else:
        print("✅ All NLTK data packages downloaded successfully!")
        return 0

if __name__ == "__main__":
    sys.exit(download_nltk_data())
