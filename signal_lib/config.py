import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
DB_PATH = os.path.join(DATA_DIR, "reports.db")

CRAWL_DELAY_MIN = 1.0
CRAWL_DELAY_MAX = 2.0
MAX_RETRIES = 3
DEFAULT_PAGES = 20

NAVER_RESEARCH_URL = "https://finance.naver.com/research/company_list.naver"
HANKYUNG_CONSENSUS_URL = "https://consensus.hankyung.com/apps.analysis/analysis.list"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
