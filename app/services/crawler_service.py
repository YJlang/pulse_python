"""
Naver and Kakao review crawling service.
"""

import asyncio
import hashlib
import re
import sys
import threading
from datetime import datetime
from typing import Dict, List
from urllib.parse import quote

from playwright.async_api import Page, async_playwright

from app.utils.logger import get_logger

logger = get_logger(__name__)


class CrawlerService:
    NAVER_REVIEW_CARD_SELECTOR = "li.place_apply_pui.EjjAW"
    NAVER_DETAIL_LINK_SELECTOR = 'a[href*="/restaurant/"], a[href*="/place/"]'
    NAVER_EXPAND_TEXT_SELECTORS = (
        "a.pui__wFzIYl",
        "a.fvwqf",
        "a.Kv9y6",
    )

    @staticmethod
    def _normalize_search_text(text: str) -> str:
        cleaned = re.sub(r"\([^)]*\)", " ", text or "")
        cleaned = re.sub(r"\b\d+\s*번길\b", " ", cleaned)
        cleaned = re.sub(r"[^\w\s가-힣-]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    # Keep a UTF-8-safe normalizer here because the legacy regex above can be
    # corrupted on Windows terminals and strip Hangul from search queries.
    @staticmethod
    def _normalize_search_text(text: str) -> str:
        cleaned = re.sub(r"\([^)]*\)", " ", text or "")
        cleaned = re.sub(r"[^0-9A-Za-z\uAC00-\uD7A3\s]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    @classmethod
    def _build_search_query(
        cls,
        store_name: str,
        address: str,
        include_address: bool = True,
    ) -> str:
        normalized_store = cls._normalize_search_text(store_name)
        normalized_address = cls._normalize_search_text(address)
        address_parts = normalized_address.split()
        concise_address = " ".join(address_parts[:4]) if address_parts else ""
        if include_address and normalized_store and concise_address:
            return f"{normalized_store} {concise_address}".strip()
        return normalized_store or concise_address

    @classmethod
    def _compact_search_text(cls, text: str) -> str:
        return re.sub(r"\s+", "", cls._normalize_search_text(text).lower())

    @classmethod
    def _tokenize_search_text(cls, text: str, limit: int | None = None) -> List[str]:
        tokens = [
            token
            for token in cls._compact_search_text(text).split()
            if token
        ]
        if not tokens:
            tokens = [
                token
                for token in (
                    cls._compact_search_text(chunk)
                    for chunk in cls._normalize_search_text(text).lower().split()
                )
                if len(token) >= 2
            ]
        return tokens[:limit] if limit is not None else tokens

    @classmethod
    def _build_match_context(cls, store_name: str, address: str) -> Dict[str, object]:
        store_tokens = [
            token
            for token in (
                cls._compact_search_text(chunk)
                for chunk in cls._normalize_search_text(store_name).lower().split()
            )
            if len(token) >= 2
        ]
        address_tokens = [
            token
            for token in (
                cls._compact_search_text(chunk)
                for chunk in cls._normalize_search_text(address).lower().split()
            )
            if len(token) >= 2
        ][:5]
        branch_tokens = store_tokens[1:] if len(store_tokens) > 1 else store_tokens
        return {
            "store_compact": cls._compact_search_text(store_name),
            "store_tokens": store_tokens,
            "branch_tokens": branch_tokens,
            "address_tokens": address_tokens,
        }

    @classmethod
    def _score_search_candidate(cls, candidate: Dict[str, str], store_name: str, address: str) -> int:
        match_context = cls._build_match_context(store_name, address)
        title_compact = cls._compact_search_text(candidate.get("title", ""))
        address_compact = cls._compact_search_text(candidate.get("address", ""))
        context_compact = cls._compact_search_text(candidate.get("context", ""))
        merged_compact = " ".join(
            value
            for value in (title_compact, address_compact, context_compact)
            if value
        )

        score = 0
        store_compact = match_context["store_compact"]
        if store_compact:
            if title_compact == store_compact:
                score += 160
            elif store_compact in title_compact:
                score += 120
            elif store_compact in merged_compact:
                score += 80

        brand_tokens = match_context["store_tokens"]
        if brand_tokens:
            brand_token = brand_tokens[0]
            if brand_token in title_compact:
                score += 12
            elif brand_token in merged_compact:
                score += 6

        for token in match_context["branch_tokens"]:
            if token in title_compact:
                score += 36
            elif token in merged_compact:
                score += 18

        address_hits = 0
        for token in match_context["address_tokens"]:
            if token in address_compact:
                score += 14
                address_hits += 1
            elif token in merged_compact:
                score += 8
                address_hits += 1

        if address_hits >= 2:
            score += 24
        if address_hits >= 3:
            score += 18

        return score

    @classmethod
    def _select_best_candidate(
        cls,
        candidates: List[Dict[str, str]],
        store_name: str,
        address: str,
    ) -> Dict[str, str] | None:
        scored_candidates = []
        for candidate in candidates:
            scored_candidate = dict(candidate)
            scored_candidate["match_score"] = cls._score_search_candidate(
                candidate,
                store_name,
                address,
            )
            scored_candidates.append(scored_candidate)

        if not scored_candidates:
            return None

        scored_candidates.sort(key=lambda candidate: candidate.get("match_score", 0), reverse=True)
        return scored_candidates[0]

    @staticmethod
    def _clean_review_text(text: str) -> str:
        cleaned = (text or "").replace("더보기", " ").replace("펼쳐보기", " ")
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    @staticmethod
    def _normalize_review_date(date_text: str | None) -> str | None:
        if not date_text:
            return None

        compact = re.sub(r"\s+", "", date_text)

        korean_match = re.search(r"(\d{4})년(\d{1,2})월(\d{1,2})일", compact)
        if korean_match:
            year, month, day = korean_match.groups()
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

        full_match = re.search(r"(\d{4})[.-](\d{1,2})[.-](\d{1,2})", compact)
        if full_match:
            year, month, day = full_match.groups()
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

        short_match = re.search(r"(\d{2})[.-](\d{1,2})[.-](\d{1,2})", compact)
        if short_match:
            year, month, day = short_match.groups()
            return f"{2000 + int(year):04d}-{int(month):02d}-{int(day):02d}"

        return None

    @staticmethod
    def _build_review_id(source: str, raw_text: str, date: str | None, author: str | None) -> str:
        base = f"{source}|{date or ''}|{author or ''}|{raw_text.strip()}".lower()
        return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _build_source_label(source: str) -> str:
        return "네이버" if source == "naver" else "카카오"

    @staticmethod
    def _sort_reviews_by_latest(reviews: List[Dict]) -> List[Dict]:
        def sort_key(review: Dict):
            return review.get("date") or "0000-00-00"

        return sorted(reviews, key=sort_key, reverse=True)

    async def _extract_naver_reviews_from_dom(self, page: Page) -> List[Dict]:
        raw_reviews = await page.evaluate(
            f"""
            () => Array.from(document.querySelectorAll('{self.NAVER_REVIEW_CARD_SELECTOR}')).map((card) => {{
              const author =
                card.querySelector('.pui__JiVbY3')?.innerText?.trim() ||
                card.querySelector('.pui__uslU0d')?.innerText?.trim() ||
                '';

              const text =
                card.querySelector('.pui__vn15t2 > a')?.innerText?.trim() ||
                card.querySelector('.pui__vn15t2')?.innerText?.trim() ||
                '';

              const dateText =
                card.querySelector('.pui__QKE5Pr')?.innerText?.trim() ||
                card.querySelector('.pui__gfuUIT')?.innerText?.trim() ||
                '';

              return {{
                rawText: card.innerText || '',
                author,
                text,
                dateText,
                hasPhoto: card.innerText.includes('사진') || card.querySelectorAll('img').length > 0,
              }};
            }});
            """
        )

        reviews: List[Dict] = []
        for raw_review in raw_reviews:
            text = self._clean_review_text(raw_review.get("text") or "")
            if len(text) < 2:
                continue

            author = (raw_review.get("author") or "").strip() or "네이버 리뷰어"
            date = self._normalize_review_date(raw_review.get("dateText"))
            raw_text = raw_review.get("rawText") or text
            review_id = self._build_review_id("naver", text, date, author)
            reviews.append(
                {
                    "id": review_id,
                    "raw_text": raw_text,
                    "text": text,
                    "rating": None,
                    "date": date,
                    "source": "naver",
                    "source_label": self._build_source_label("naver"),
                    "author": author,
                    "has_photo": bool(raw_review.get("hasPhoto")),
                }
            )

        return reviews

    async def _click_visible_elements(self, page: Page, selector: str, max_clicks: int = 20) -> int:
        locator = page.locator(selector)
        click_count = 0
        total = await locator.count()

        for index in range(min(total, max_clicks)):
            element = locator.nth(index)
            try:
                if not await element.is_visible():
                    continue
                await element.click(timeout=600)
                click_count += 1
                await page.wait_for_timeout(100)
            except Exception:
                continue

        return click_count

    async def _extract_naver_search_candidates(self, page: Page) -> List[Dict[str, str]]:
        return await page.evaluate(
            """
            () => {
              const candidates = [];
              const seen = new Set();
              const links = Array.from(
                document.querySelectorAll('a[href*="/restaurant/"], a[href*="/place/"]')
              );

              for (const link of links) {
                const href = link.getAttribute('href') || '';
                if (!/^\\/(restaurant|place)\\/\\d+(?:\\?.*)?$/.test(href)) {
                  continue;
                }

                const absoluteHref = href.startsWith('http')
                  ? href
                  : `https://m.place.naver.com${href}`;
                const dedupeKey = absoluteHref.split('?')[0];
                if (seen.has(dedupeKey)) {
                  continue;
                }

                seen.add(dedupeKey);
                const container =
                  link.closest('li') ||
                  link.closest('article') ||
                  link.parentElement;

                candidates.push({
                  href: absoluteHref,
                  title: (link.innerText || '').trim(),
                  address: '',
                  context: (container?.innerText || '').trim(),
                });

                if (candidates.length >= 10) {
                  break;
                }
              }

              return candidates;
            }
            """
        )

    async def _extract_kakao_search_candidates(self, page: Page) -> List[Dict[str, str]]:
        return await page.evaluate(
            """
            () => Array.from(document.querySelectorAll('li[data-id]')).slice(0, 10).map((item) => ({
              data_id: item.getAttribute('data-id') || '',
              title:
                item.querySelector('strong')?.innerText?.trim() ||
                item.querySelector('.tit_location')?.innerText?.trim() ||
                '',
              address:
                item.querySelector('.txt_address')?.innerText?.trim() ||
                item.querySelector('.addr')?.innerText?.trim() ||
                '',
              context: (item.innerText || '').trim(),
            })).filter((candidate) => candidate.data_id);
            """
        )

    async def _resolve_naver_detail_url(self, page: Page, store_name: str, address: str) -> str | None:
        path = page.url.split("?", 1)[0]
        if re.search(r"/(?:restaurant|place)/\d+$", path):
            return page.url

        candidates = await self._extract_naver_search_candidates(page)
        best_candidate = self._select_best_candidate(candidates, store_name, address)
        if best_candidate:
            logger.info(
                "[Naver] Selected candidate: %s (score=%s)",
                best_candidate.get("title") or best_candidate.get("href"),
                best_candidate.get("match_score", 0),
            )
            return best_candidate.get("href")

        return None

    async def crawl_naver(self, store_name: str, address: str, max_reviews: int = 80) -> List[Dict]:
        query = self._build_search_query(store_name, address)
        logger.info("[Naver] Searching for: %s", query)
        reviews: List[Dict] = []
        seen_ids = set()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
                viewport={"width": 375, "height": 812},
            )
            page = await context.new_page()

            try:
                search_url = f"https://m.place.naver.com/restaurant/list?query={quote(query)}"
                await page.goto(search_url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2500)

                detail_url = await self._resolve_naver_detail_url(page, store_name, address)
                if not detail_url:
                    logger.warning("[Naver] No detail page found from search results.")
                    return []

                await page.goto(detail_url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(1200)

                place_match = re.search(r"/(?:restaurant|place)/(\d+)", page.url)
                if not place_match:
                    logger.warning("[Naver] Failed to resolve place id from %s", page.url)
                    return []

                place_id = place_match.group(1)
                review_url = f"https://m.place.naver.com/restaurant/{place_id}/review/visitor?entry=ple"
                await page.goto(review_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(4000)

                stagnant_rounds = 0
                max_rounds = 12

                while len(reviews) < max_reviews and stagnant_rounds < max_rounds:
                    before_count = len(reviews)

                    for selector in self.NAVER_EXPAND_TEXT_SELECTORS:
                        await self._click_visible_elements(page, selector)

                    extracted_reviews = await self._extract_naver_reviews_from_dom(page)
                    for review in extracted_reviews:
                        if review["id"] in seen_ids:
                            continue
                        seen_ids.add(review["id"])
                        reviews.append(review)

                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1800)

                    if len(reviews) == before_count:
                        stagnant_rounds += 1
                    else:
                        stagnant_rounds = 0

                reviews = self._sort_reviews_by_latest(reviews)
                logger.info("[Naver] Collected %s reviews", len(reviews))
            except Exception as exc:
                logger.error("[Naver] Crawling error: %s", exc)
            finally:
                await browser.close()

        return reviews[:max_reviews]

    async def crawl_kakao(self, store_name: str, address: str, max_reviews: int = 80) -> List[Dict]:
        query = self._build_search_query(store_name, address, include_address=False)
        logger.info("[Kakao] Searching for: %s", query)
        reviews: List[Dict] = []
        seen_ids = set()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
                viewport={"width": 375, "height": 812},
            )
            page = await context.new_page()

            try:
                search_url = f"https://m.map.kakao.com/actions/searchView?q={quote(query)}"
                await page.goto(search_url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000)

                candidates = await self._extract_kakao_search_candidates(page)
                if not candidates:
                    logger.warning("[Kakao] No search results found.")
                    return []

                best_candidate = self._select_best_candidate(candidates, store_name, address)
                if not best_candidate:
                    logger.warning("[Kakao] No candidate matched the requested store.")
                    return []

                logger.info(
                    "[Kakao] Selected candidate: %s (score=%s)",
                    best_candidate.get("title") or best_candidate.get("data_id"),
                    best_candidate.get("match_score", 0),
                )

                data_id = best_candidate.get("data_id")
                review_url = f"https://place.map.kakao.com/{data_id}#review"
                await page.goto(review_url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2500)

                stagnant_rounds = 0
                max_rounds = 35
                while len(reviews) < max_reviews and stagnant_rounds < max_rounds:
                    before_count = len(reviews)
                    review_items = page.locator("ul.list_review > li")
                    item_count = await review_items.count()

                    for index in range(item_count):
                        item = review_items.nth(index)
                        try:
                            review_text_block = item.locator("p.desc_review").first
                            if await review_text_block.count() == 0:
                                continue

                            more = review_text_block.locator(".btn_more").first
                            if await more.count() > 0 and await more.is_visible():
                                await more.click(timeout=800)
                                await page.wait_for_timeout(100)

                            text = (await review_text_block.inner_text()).replace("더보기", "").strip()
                            if not text:
                                continue

                            author = "카카오 리뷰어"
                            try:
                                author_text = await item.locator(".link_user, .name_user, strong").first.inner_text()
                                author = author_text.strip() or author
                            except Exception:
                                pass

                            date = None
                            try:
                                date_text = await item.locator(".txt_date").first.inner_text()
                                date = self._normalize_review_date(date_text)
                            except Exception:
                                date = None

                            rating = None
                            try:
                                spans = await item.locator(".starred_grade .screen_out").all()
                                for span in spans:
                                    star_text = await span.inner_text()
                                    if star_text.replace(".", "").isdigit():
                                        rating = float(star_text)
                                        break
                            except Exception:
                                rating = None

                            review_id = self._build_review_id("kakao", text, date, author)
                            if review_id in seen_ids:
                                continue

                            has_photo = False
                            try:
                                has_photo = await item.locator("a.link_photo, ul.list_photo img, span.ico_photo").count() > 0
                            except Exception:
                                has_photo = False

                            reviews.append(
                                {
                                    "id": review_id,
                                    "raw_text": text,
                                    "text": text,
                                    "rating": rating,
                                    "date": date,
                                    "source": "kakao",
                                    "source_label": self._build_source_label("kakao"),
                                    "author": author,
                                    "has_photo": has_photo,
                                }
                            )
                            seen_ids.add(review_id)
                        except Exception:
                            continue

                        if len(reviews) >= max_reviews:
                            break

                    try:
                        more_link = page.locator("a.link_more:has-text('후기 더보기'), a.link_more:has-text('더보기')").first
                        if await more_link.count() > 0 and await more_link.is_visible():
                            await more_link.click()
                            await page.wait_for_timeout(900)
                    except Exception:
                        pass

                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1000)

                    if len(reviews) == before_count:
                        stagnant_rounds += 1
                    else:
                        stagnant_rounds = 0

                reviews = self._sort_reviews_by_latest(reviews)
                logger.info("[Kakao] Collected %s reviews", len(reviews))
            except Exception as exc:
                logger.error("[Kakao] Crawling error: %s", exc)
            finally:
                await browser.close()

        return reviews[:max_reviews]

    async def collect_all_reviews(self, store_name: str, address: str) -> List[Dict]:
        query = self._build_search_query(store_name, address)
        logger.info("Starting concurrent crawling for: %s", query)

        async def _crawl_all():
            naver_task = asyncio.create_task(self.crawl_naver(store_name, address, max_reviews=80))
            kakao_task = asyncio.create_task(self.crawl_kakao(store_name, address, max_reviews=80))
            return await asyncio.gather(naver_task, kakao_task)

        if sys.platform == "win32":
            result_container = {}

            def _run_in_thread():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    if not isinstance(loop, asyncio.ProactorEventLoop):
                        loop.close()
                        loop = asyncio.ProactorEventLoop()
                        asyncio.set_event_loop(loop)
                    result_container["result"] = loop.run_until_complete(_crawl_all())
                except Exception as exc:
                    result_container["error"] = exc
                finally:
                    loop.close()

            thread = threading.Thread(target=_run_in_thread)
            thread.start()

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, thread.join)

            if "error" in result_container:
                raise result_container["error"]
            results = result_container["result"]
        else:
            results = await _crawl_all()

        all_reviews = results[0] + results[1]
        logger.info(
            "Total reviews collected: %s (Naver: %s, Kakao: %s)",
            len(all_reviews),
            len(results[0]),
            len(results[1]),
        )
        return all_reviews
