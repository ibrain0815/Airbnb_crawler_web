"""
에어비앤비 숙소 목록 크롤러
FastAPI 백엔드용 — headless Chrome 전용, 페이지 단위 수집 및 다음 페이지 이동.
봇 감지 우회: CDP로 navigator.webdriver 숨김, 랜덤 지연, (선택) undetected-chromedriver.
"""

import logging
import os
import random
import re
import time
from typing import Any, Callable

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)

# 실제 Chrome User-Agent (최신 버전) — 고정 사용
CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 에어비앤비 검색 결과 페이지 — 실제 HTML: title_ID, price-availability-row, 총액 span[aria-label*="총액"], 평점 span.a8jt5op / span[aria-hidden="true"]
SELECTORS = {
    "listing_card": [
        'a[href*="/rooms/"][aria-labelledby^="title_"]',
        'a[href*="/rooms/"]',
        '[data-testid="listing-card"]',
        'div[class*="listing-card"]',
    ],
    "title": [
        '[id^="title_"]',
        '[data-testid="listing-card-title"]',
        'span[class*="title"]',
        'div[class*="title"]',
        'h2',
    ],
    "price": [
        '[data-testid="price-availability-row"] span[aria-label*="총액"]',
        '[data-testid="price-availability-row"] span.sjwpj0z',
        '[data-testid="price-availability-row"] span.u174bpcy',  # 총액 금액만 있는 span (라벨 없음)
        'span[aria-label*="총액"]',
        'span[class*="price"]',
        '[data-testid="listing-card-price"]',
    ],
    "rating": [
        'span.a8jt5op',  # "평점 4.88점(5점 만점), 후기 550개"
        '.t1phmnpa span[aria-hidden="true"]',  # "4.88 (550)"
        '.r4a59j5 span',
        '[data-testid="listing-card-rating"]',
        'span[class*="rating"]',
        'span[aria-label*="rating"]',
    ],
    "address_location": [
        '[data-testid="listing-card-subtitle"] span[data-testid="listing-card-name"]',
        'div[class*="location"]',
        'span[class*="location"]',
        '[data-testid="listing-card-location"]',
        'div[class*="address"]',
    ],
    "next_page": [
        'a[aria-label*="다음"]',
        'a[aria-label*="Next"]',
        'button[aria-label*="다음"]',
        '[class*="pagination"] a:last-child',
        'a[href*="items_offset"]',
    ],
}


def _apply_stealth_cdp(driver: webdriver.Chrome) -> None:
    """
    CDP로 페이지 로드 시 navigator.webdriver 를 숨겨 봇 감지 완화.
    Chrome 79+ 에서 동작.
    """
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": (
                    "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
                )
            },
        )
    except Exception as e:
        logger.debug("CDP stealth 적용 실패(무시 가능): %s", e)


def create_driver() -> webdriver.Chrome:
    """
    headless Chrome 드라이버 생성.
    봇 감지 우회: --disable-blink-features=AutomationControlled, CDP로 webdriver 속성 숨김.
    환경변수 USE_UNDETECTED_CHROME=1 이면 undetected_chromedriver 사용(감지 우회 강화).
    """
    use_uc = os.environ.get("USE_UNDETECTED_CHROME", "").strip().lower() in ("1", "true", "yes")

    if use_uc:
        try:
            import undetected_chromedriver as uc
            opts = uc.ChromeOptions()
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument("--lang=ko-KR")
            driver = uc.Chrome(options=opts, headless=True)
            driver.implicitly_wait(3)
            _apply_stealth_cdp(driver)
            return driver
        except Exception as e:
            logger.warning("undetected_chromedriver 생성 실패, 일반 Chrome 사용: %s", e)

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ko-KR")
    options.add_argument(f"user-agent={CHROME_USER_AGENT}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    _apply_stealth_cdp(driver)
    driver.implicitly_wait(3)
    return driver


def _get_text_from_card(card: Any, key: str, root: Any = None) -> str:
    """카드(또는 root) 요소에서 텍스트 추출 — fallback 순서대로 시도."""
    search_root = root if root is not None else card
    for selector in SELECTORS.get(key, []):
        try:
            elem = search_root.find_element(By.CSS_SELECTOR, selector)
            text = (elem.text or "").strip()
            if text:
                return text
        except NoSuchElementException:
            continue
    return ""


def _get_title_from_card(driver: Any, card: Any, root: Any = None) -> str:
    """제목 추출. 실제 HTML: <a aria-labelledby="title_910372965352828346"> → id로 가리키는 요소 텍스트."""
    try:
        labelledby = card.get_attribute("aria-labelledby")
        if labelledby and labelledby.startswith("title_"):
            title_el = driver.find_element(By.ID, labelledby)
            text = (title_el.text or "").strip()
            if text:
                return text
    except NoSuchElementException:
        pass
    return _get_text_from_card(card, "title", root)


def _get_link_from_card(card: Any, base_url: str = "") -> str:
    """숙소 상세 링크. 카드가 <a href="/rooms/ID?..."> 이면 href 사용 (상대 경로 시 base_url 붙임)."""
    try:
        if card.tag_name.lower() == "a":
            href = (card.get_attribute("href") or "").strip()
            if href and href.startswith("http"):
                return href
            if href and base_url:
                return (base_url.rstrip("/") + href) if href.startswith("/") else (base_url + href)
            return href
        link = card.find_element(By.CSS_SELECTOR, 'a[href*="/rooms/"]')
        return (link.get_attribute("href") or "").strip()
    except NoSuchElementException:
        pass
    try:
        link = card.find_element(By.TAG_NAME, "a")
        return (link.get_attribute("href") or "").strip()
    except NoSuchElementException:
        pass
    return ""


def _room_id_from_href(href: str) -> str:
    """href에서 방 ID 추출. /rooms/9977181?... -> 9977181"""
    if not href or "/rooms/" not in href:
        return ""
    part = href.split("/rooms/")[-1].split("?")[0].strip("/")
    return part or ""


# 한 번의 스크립트 실행으로 페이지 전체 카드 수집 (실제 HTML: title_ID, price-availability-row, 총액, 평점)
_FAST_SCRAPE_SCRIPT = """
var cards = document.querySelectorAll('a[href*="/rooms/"][aria-labelledby^="title_"]');
var seen = {}, out = [];
for (var i = 0; i < cards.length; i++) {
  var a = cards[i];
  var href = (a.getAttribute('href') || '').trim();
  var roomId = href.split('/rooms/')[1];
  if (roomId) roomId = roomId.split('?')[0];
  if (!roomId || seen[roomId]) continue;
  seen[roomId] = true;
  var titleId = a.getAttribute('aria-labelledby');
  var title = '';
  var cardRoot = a.parentElement;
  if (titleId) {
    var te = document.getElementById(titleId);
    if (te) {
      title = (te.textContent || '').trim();
      for (var w = te.parentElement; w && w !== document.body; w = w.parentElement) {
        if (w.querySelector('[data-testid="price-availability-row"]')) { cardRoot = w; break; }
      }
    }
  }
    var price = '', totalPrice = '', rating = '', address = '';
  if (cardRoot) {
    var priceRow = cardRoot.querySelector('[data-testid="price-availability-row"]');
    if (priceRow) {
      var totalSpan = priceRow.querySelector('span[aria-label*="총액"], [aria-label*="총액"]');
      if (totalSpan) {
        totalPrice = (totalSpan.textContent || '').trim();
        if (!price) price = totalPrice;
      }
      if (!totalPrice) {
        var amountSpan = priceRow.querySelector('span.u174bpcy');
        if (amountSpan) {
          totalPrice = (amountSpan.textContent || '').trim();
          if (!price) price = totalPrice;
        }
      }
      if (!totalPrice) {
        var allSpans = priceRow.querySelectorAll('span');
        for (var s = 0; s < allSpans.length; s++) {
          var t = (allSpans[s].textContent || '').trim();
          if (t.charAt(0) === '\u20a9' && t.length < 20) {
            totalPrice = t;
            if (!price) price = t;
            break;
          }
        }
      }
      var otherPrice = priceRow.querySelector('span.sjwpj0z');
      if (otherPrice && !price) price = (otherPrice.textContent || '').trim();
    }
    if (!totalPrice) {
      var tp = cardRoot.querySelector('span[aria-label*="총액"], [aria-label*="총액"]');
      if (tp) totalPrice = (tp.textContent || '').trim();
    }
    if (!totalPrice) {
      var uSpan = cardRoot.querySelector('span.u174bpcy');
      if (uSpan) totalPrice = (uSpan.textContent || '').trim();
      if (!price) price = totalPrice;
    }
    if (!price) {
      var pe = cardRoot.querySelector('[class*="price"], [data-testid="listing-card-price"]');
      if (pe) price = (pe.textContent || '').trim();
    }
    var ratingSpan = cardRoot.querySelector('span.a8jt5op');
    if (ratingSpan && (ratingSpan.textContent || '').indexOf('평점') !== -1) rating = (ratingSpan.textContent || '').trim();
    if (!rating) {
      var hidden = cardRoot.querySelectorAll('.t1phmnpa span[aria-hidden="true"], .r4a59j5 span[aria-hidden="true"]');
      for (var h = 0; h < hidden.length; h++) {
        var t = (hidden[h].textContent || '').trim();
        if (/^\\d+\\.\\d+\\s*\\(\\d+\\)$/.test(t)) { rating = t; break; }
      }
    }
    if (!rating) {
      var re = cardRoot.querySelector('[class*="rating"], [class*="review"]');
      if (re) rating = (re.textContent || '').trim();
    }
    var le = cardRoot.querySelector('[data-testid="listing-card-name"], [class*="location"], [data-testid="listing-card-location"]');
    if (le) address = (le.textContent || '').trim();
  }
  out.push({ href: href, title: title, price: price, rating: rating, address: address });
}
return out;
"""


def _get_airbnb_listings_fast(driver: webdriver.Chrome, base_url: str) -> list[dict] | None:
    """
    execute_script 한 번으로 전체 카드 수집. 성공 시 리스트 반환, 실패 시 None.
    """
    try:
        raw = driver.execute_script(_FAST_SCRAPE_SCRIPT)
        if not raw or not isinstance(raw, list):
            return None
        listings = []
        for i, row in enumerate(raw):
            href = (row.get("href") or "").strip()
            if not href:
                continue
            url = (base_url.rstrip("/") + href) if href.startswith("/") else (base_url + href)
            title = (row.get("title") or "").strip() or f"숙소 {i+1}"
            listings.append({
                "no": len(listings) + 1,
                "title": title,
                "price": (row.get("price") or "").strip(),
                "address": (row.get("address") or "").strip(),
                "rating": (row.get("rating") or "").strip(),
                "url": url,
            })
        if listings:
            logger.info("고속 수집: %d개 카드 (execute_script 1회)", len(listings))
        return listings if listings else None
    except Exception as e:
        logger.debug("고속 수집 실패, fallback 사용: %s", e)
        return None


def get_airbnb_listings(driver: webdriver.Chrome) -> list[dict]:
    """
    현재 페이지에서 에어비앤비 숙소 목록 수집.
    먼저 execute_script 한 번으로 고속 수집 시도, 실패 시 요소별 fallback.
    """
    current = driver.current_url or ""
    base_match = re.match(r"^https?://[^/]+", current)
    base_url = base_match.group(0) if base_match else "https://www.airbnb.co.kr"

    # 1) 고속 경로: 스크립트 1회로 전체 수집 (a[href*="/rooms/"][aria-labelledby^="title_"] 구조)
    fast = _get_airbnb_listings_fast(driver, base_url)
    if fast is not None:
        return fast

    # 2) Fallback: 요소별 수집
    listings: list[dict] = []
    wait = WebDriverWait(driver, 10)
    cards: list[Any] = []
    for selector in SELECTORS["listing_card"]:
        try:
            cards = wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector))
            )
            if cards:
                logger.info("listing_card: %s 로 카드 %d개 발견", selector, len(cards))
                break
        except TimeoutException:
            continue

    if not cards:
        logger.warning("숙소 카드를 찾을 수 없습니다. 다른 선택자 시도.")
        for sel in ["a[href*='/rooms/']", "div[class*='listing']", "article"]:
            try:
                cards = driver.find_elements(By.CSS_SELECTOR, sel)
                if len(cards) > 1:
                    break
            except Exception:
                continue

    seen_ids: set[str] = set()
    for i, card in enumerate(cards):
        try:
            url = _get_link_from_card(card, base_url)
            room_id = _room_id_from_href(url)
            if room_id and room_id in seen_ids:
                continue
            if room_id:
                seen_ids.add(room_id)

            # 제목: aria-labelledby → id 요소 텍스트 우선
            title = _get_title_from_card(driver, card, None)
            if not title:
                title = (card.text or "").strip() or f"숙소 {len(listings)+1}"

            # 가격/평점/주소: 카드가 <a>면 부모에서 찾기 (실제 DOM 구조)
            root = card
            if card.tag_name.lower() == "a":
                try:
                    parent = card.find_element(By.XPATH, "..")
                    root = parent
                except NoSuchElementException:
                    pass
            price = _get_text_from_card(card, "price", root)
            rating = _get_text_from_card(card, "rating", root)
            address = _get_text_from_card(card, "address_location", root)

            if not url and not title:
                continue
            listings.append({
                "no": len(listings) + 1,
                "title": title or "",
                "price": price or "",
                "address": address or "",
                "rating": rating or "",
                "url": url or "",
            })
        except Exception as e:
            logger.warning("숙소 카드 추출 실패: %s", e)
            continue

    return listings


def go_to_next_page(driver: webdriver.Chrome) -> bool:
    """
    다음 검색 결과 페이지로 이동.
    '다음' 버튼 또는 items_offset 링크 클릭. 성공 시 True.
    """
    for selector in SELECTORS["next_page"]:
        try:
            elem = driver.find_element(By.CSS_SELECTOR, selector)
            if elem.is_displayed() and elem.is_enabled():
                elem.click()
                time.sleep(random.uniform(1.0, 2.0))
                return True
        except NoSuchElementException:
            continue
        except Exception as e:
            logger.debug("다음 페이지 선택자 실패 %s: %s", selector, e)
            continue

    # 스크롤로 추가 로드 시도 (무한 스크롤 페이지)
    try:
        prev_height = driver.execute_script("return document.body.scrollHeight")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(random.uniform(1.0, 2.0))
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height > prev_height:
            return True
    except Exception:
        pass
    return False


def run_crawl(
    search_url: str,
    max_pages: int,
    on_page_result: Callable[[int, list[dict], list[dict]], None] | None = None,
) -> list[dict]:
    """
    driver 생성 → URL 이동 → 쿠키/로딩 대기 → 페이지 루프(수집 + 다음 페이지) → driver 종료.
    각 페이지 수집 결과는 on_page_result(현재페이지, 해당페이지_리스트, 전체_누적_리스트) 로 콜백.
    try/finally 로 driver 는 반드시 종료.
    """
    driver = None
    all_listings: list[dict] = []
    try:
        driver = create_driver()
        logger.info("검색 URL 이동: %s", search_url)
        driver.get(search_url)
        time.sleep(random.uniform(2.0, 4.0))  # 봇 감지 우회: 첫 로드 후 인간형 지연

        for page in range(1, max_pages + 1):
            logger.info("페이지 %d/%d 수집 중", page, max_pages)
            page_listings = get_airbnb_listings(driver)
            if not page_listings and page == 1:
                logger.warning("첫 페이지에서 목록을 찾지 못했습니다.")
                break
            for idx, item in enumerate(page_listings):
                item["no"] = len(all_listings) + idx + 1
            all_listings.extend(page_listings)
            if on_page_result:
                try:
                    on_page_result(page, page_listings, all_listings)
                except Exception as e:
                    logger.warning("on_page_result 콜백 오류: %s", e)
            if page < max_pages and not go_to_next_page(driver):
                logger.info("다음 페이지 없음, 크롤링 종료.")
                break
            time.sleep(random.uniform(1.0, 2.5))  # 페이지 간 랜덤 지연으로 봇 패턴 완화
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
            logger.info("드라이버 종료 완료")

    return all_listings
