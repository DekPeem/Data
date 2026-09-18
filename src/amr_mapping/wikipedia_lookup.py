"""ค้นหาข้อมูลบริษัทจาก Wikipedia ภาษาไทย — ใช้เป็นอีกช่องทาง "ฟรี ไม่มีค่าใช้จ่าย" เวลา DBD
DataWarehouse บล็อกอยู่ (ดู dbd_lookup.BlockedByAntiBot) เสริมจาก dataforthai.com fallback และ
ฐานข้อมูล DBD Open Data ในเครื่อง (ดู dbd_opendata.py)

⚠️ ครอบคลุมเฉพาะบริษัทใหญ่/มีชื่อเสียงที่มีหน้า Wikipedia เท่านั้น — บังเอิญเป็นกลุ่มเดียวกับที่
ฐานข้อมูล DBD Open Data ในเครื่องมักหาไม่เจอพอดี (เพราะเป็นบริษัทเก่าที่จดทะเบียนมานาน ไม่ใช่
"ตั้งใหม่/เลิกกิจการ" ในช่วงที่ดึงข้อมูลมา) จึงช่วยเติมเต็มจุดที่ยังขาดได้บางส่วนแบบไม่ต้องเสียเงิน
— บริษัทเล็ก/กลาง/ทั่วไปส่วนใหญ่จะไม่มีหน้า Wikipedia เลย ต้องพึ่งช่องทางอื่นแทน

Wikipedia (มูลนิธิ Wikimedia) เปิด API สาธารณะให้ใช้ฟรีโดยเจตนา ไม่มีระบบป้องกันบอทแบบ Incapsula/
Cloudflare Turnstile — แค่ต้องส่ง User-Agent ที่ระบุตัวตนชัดเจนตามนโยบายของเขา (ดู
https://meta.wikimedia.org/wiki/User-Agent_policy) ไม่ใช่การเลี่ยงระบบป้องกันบอทแต่อย่างใด

ขั้นตอน:
    1. GET https://th.wikipedia.org/w/api.php?action=query&list=search&srsearch=<ชื่อบริษัท>
       ค้นหาหน้าที่ชื่อใกล้เคียงที่สุด คืนรายการ title
    2. GET https://th.wikipedia.org/w/api.php?action=query&prop=extracts&exintro=true&
       explaintext=true&titles=<title จากข้อ 1>
       ดึงข้อความสรุปย่อหน้าแรกของหน้านั้น (plain text ไม่มี markup)

คืนแค่ข้อความอิสระ (เหมือน dataforthai.com's business_category) ไม่ใช่รหัส TSIC ที่แม่นยำ — จึง
จับคู่ประเภทธุรกิจในระบบเราให้อัตโนมัติไม่ได้ ใช้เป็นข้อมูลประกอบให้ผู้ใช้อ่านแล้วเลือกเองเท่านั้น

⚠️ ยังไม่เคยทดสอบดึงข้อมูลจริงจากเว็บนี้เลย — สภาพแวดล้อมที่พัฒนาโค้ดนี้ต่อ th.wikipedia.org ไม่ได้
(โดน proxy บล็อกด้วย 403 เหมือนที่เจอกับ openapi.dbd.go.th/data.go.th ก่อนหน้านี้) เขียนโค้ดแบบ
ป้องกัน error ให้มากที่สุดเท่าที่ทำได้ แต่ยังไม่ยืนยันว่ารูปแบบ response จริงตรงกับที่เขียนไว้ 100%
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

BASE_URL = "https://th.wikipedia.org"
API_URL = f"{BASE_URL}/w/api.php"

# Wikipedia กำหนดให้ระบุตัวตน/ช่องทางติดต่อใน User-Agent (นโยบายสาธารณะของ Wikimedia ไม่ใช่การ
# ปลอมตัวเป็นเบราว์เซอร์แต่อย่างใด — ตรงข้ามกับ dataforthai_lookup.py ที่ต้องใช้ User-Agent แบบ
# เบราว์เซอร์จริงเพราะนั่นคือ endpoint ภายในของเว็บนั้น)
USER_AGENT = "NoAMR-Forecast-BusinessTypeLookup/1.0 (educational/internal PEA tool; no public URL)"

# ตัดข้อความสรุปให้ไม่ยาวเกินไป (บางหน้ามีย่อหน้าแรกยาวมาก) — พอให้เห็นบริบทธุรกิจคร่าวๆ
_MAX_SUMMARY_LENGTH = 500

ProgressCallback = Callable[[str], None]


def _noop(_: str) -> None:
    pass


@dataclass(frozen=True)
class WikipediaCompanyInfo:
    """ผลการค้นหาบริษัทจาก Wikipedia — summary เป็นข้อความอิสระ ไม่ใช่รหัส TSIC"""

    title: str
    summary: str
    url: str


def _get_json(url: str, timeout: float, log: ProgressCallback) -> Optional[dict]:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        log(f"⚠️ Wikipedia API ตอบกลับ HTTP {e.code}: {url}")
        return None
    except URLError as e:
        log(f"⚠️ เชื่อมต่อ Wikipedia API ไม่สำเร็จ: {e}")
        return None

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        log(f"⚠️ Wikipedia API ตอบกลับไม่ใช่ JSON ที่ถูกต้อง (เริ่มต้น: {body[:200]!r})")
        return None


def search_wikipedia_company(
    company_name: str, timeout: float = 10.0, log: ProgressCallback = _noop
) -> Optional[WikipediaCompanyInfo]:
    """ค้นหาบริษัทจากชื่อใน Wikipedia ภาษาไทย คืน None ถ้าไม่พบหรือเรียกไม่สำเร็จ (ไม่ raise —
    เป็นแค่ข้อมูลเสริมฟรี พังแล้วไม่ควรทำให้ job หลักล้มไปด้วย เหมือน dataforthai.com fallback)"""

    search_url = (
        f"{API_URL}?action=query&list=search&format=json&srlimit=1"
        f"&srsearch={quote(company_name)}"
    )
    log(f"🔎 ค้นหาใน Wikipedia (ไทย): '{company_name}'")
    search_data = _get_json(search_url, timeout, log)
    if not search_data:
        return None

    results = search_data.get("query", {}).get("search", [])
    if not results:
        log("ℹ️ ไม่พบหน้า Wikipedia ที่เกี่ยวข้อง (ปกติมากถ้าไม่ใช่บริษัทใหญ่/มีชื่อเสียง)")
        return None

    title = results[0].get("title", "").strip()
    if not title:
        return None

    extract_url = (
        f"{API_URL}?action=query&prop=extracts&exintro=true&explaintext=true&format=json"
        f"&titles={quote(title)}"
    )
    extract_data = _get_json(extract_url, timeout, log)
    if not extract_data:
        return None

    pages = extract_data.get("query", {}).get("pages", {})
    if not pages:
        return None

    page = next(iter(pages.values()))
    summary = (page.get("extract") or "").strip()
    if not summary:
        log(f"ℹ️ พบหน้า Wikipedia '{title}' แต่ไม่มีข้อความสรุป")
        return None

    if len(summary) > _MAX_SUMMARY_LENGTH:
        summary = summary[:_MAX_SUMMARY_LENGTH].rstrip() + "…"

    log(f"✅ พบข้อมูลจาก Wikipedia: '{title}'")
    return WikipediaCompanyInfo(title=title, summary=summary, url=f"{BASE_URL}/wiki/{quote(title)}")
