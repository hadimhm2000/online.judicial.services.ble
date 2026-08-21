# -*- coding: utf-8 -*-
"""
پایپ‌لاین کامل: آدرس متنی فارسی -> Geocoding با نشان -> استعلام ارزش منطقه‌ای از tax.gov.ir

نیازمندی‌ها:
    pip install requests beautifulsoup4 --break-system-packages

نکته امنیتی: کلید API نشان از متغیر محیطی NESHAN_API_KEY خوانده می‌شود.
"""

import json
import os
import logging

import requests

from tax_geolocation_query import query_location_value, get_province_id

logger = logging.getLogger(__name__)

NESHAN_API_KEY = os.environ.get("NESHAN_API_KEY", "")
NESHAN_GEOCODE_URL = "https://api.neshan.org/geocoding/v1/plus"


def geocode_address(address: str, city: str = None, province: str = None) -> dict:
    """
    آدرس متنی فارسی را با سرویس نشان به (lat, lng, province, city) تبدیل می‌کند.
    """
    if not NESHAN_API_KEY:
        raise RuntimeError("NESHAN_API_KEY تنظیم نشده است. لطفاً در فایل .env مقداردهی کنید.")

    payload = {"address": address}
    if city:
        payload["city"] = city
    if province:
        payload["province"] = province

    resp = requests.get(
        NESHAN_GEOCODE_URL,
        params={"json": json.dumps(payload, ensure_ascii=False)},
        headers={"Api-Key": NESHAN_API_KEY},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    items = data.get("items", [])
    if not items:
        raise ValueError(f"Geocoding نتیجه‌ای برنگرداند. آدرس را بررسی کنید.")

    best = items[0]
    loc = best.get("location", {})
    if "latitude" not in loc or "longitude" not in loc:
        raise ValueError(f"فرمت location ناشناخته: {loc}")

    return {
        "lat": loc["latitude"],
        "lng": loc["longitude"],
        "province": best.get("province") or province,
        "city": best.get("city") or city,
        "neighbourhood": best.get("neighbourhood"),
    }


def full_pipeline(address: str, city: str = None, province_hint: str = None) -> dict:
    """
    آدرس متنی -> مختصات (نشان) -> ارزش منطقه‌ای (tax.gov.ir)
    خروجی: دیکشنری نتیجه یا خطا در صورت عدم موفقیت هر مرحله
    """
    geo = geocode_address(address, city=city, province=province_hint)

    province_name = geo["province"] or province_hint
    if not province_name:
        raise ValueError(
            "استان از Geocoding مشخص نشد و province_hint هم داده نشده. "
            "بدون استان نمی‌شه شناسه صحیح صفحه مالیاتی رو ساخت."
        )

    province_id = get_province_id(province_name)

    with requests.Session() as session:
        tax_result = query_location_value(session, province_id, geo["lat"], geo["lng"])

    return {
        "geocoded": geo,
        "province_id": province_id,
        "tax_info": tax_result,  # حالا دیکشنری ساختاریافته است
    }
