import time
import random
import requests
from bs4 import BeautifulSoup
from signal_lib.config import USER_AGENT, CRAWL_DELAY_MIN, CRAWL_DELAY_MAX, MAX_RETRIES


class BaseCrawler:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "ko-KR,ko;q=0.9",
        })

    def fetch(self, url: str, params: dict = None, encoding: str = "euc-kr") -> BeautifulSoup:
        for attempt in range(MAX_RETRIES):
            try:
                self.polite_delay()
                resp = self.session.get(url, params=params, timeout=15)
                resp.encoding = encoding
                resp.raise_for_status()
                return BeautifulSoup(resp.text, "lxml")
            except requests.RequestException as e:
                if attempt == MAX_RETRIES - 1:
                    raise
                wait = (2 ** attempt) + random.random()
                print(f"[재시도 {attempt+1}/{MAX_RETRIES}] {e}, {wait:.1f}초 대기")
                time.sleep(wait)

    def fetch_json(self, url: str, params: dict = None) -> dict:
        for attempt in range(MAX_RETRIES):
            try:
                self.polite_delay()
                resp = self.session.get(url, params=params, timeout=15)
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                if attempt == MAX_RETRIES - 1:
                    raise
                wait = (2 ** attempt) + random.random()
                print(f"[재시도 {attempt+1}/{MAX_RETRIES}] {e}, {wait:.1f}초 대기")
                time.sleep(wait)

    def polite_delay(self):
        time.sleep(random.uniform(CRAWL_DELAY_MIN, CRAWL_DELAY_MAX))
