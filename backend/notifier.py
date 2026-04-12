"""
SIEWS+ 5.0 WhatsApp Notifier
Send alerts via Fonnte API (fonnte.com).
"""
import httpx
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional


# WIB timezone (UTC+7)
WIB = timezone(timedelta(hours=7))


async def send_whatsapp(
    phone: str,
    zone_name: str,
    risk_level: str,
    confidence: float,
    shutdown_triggered: bool,
    facility_name: str,
    fonnte_token: str,
    snapshot_url: Optional[str] = None,
) -> dict:
    """
    Send WhatsApp alert via Fonnte API.
    Returns response dict from Fonnte.
    """
    now_wib = datetime.now(WIB).strftime("%d/%m/%Y %H:%M:%S WIB")

    message = (
        f"🚨 SIEWS+ ALERT — ZONA TERLARANG DILANGGAR\n\n"
        f"Fasilitas : {facility_name}\n"
        f"Zona      : {zone_name}\n"
        f"Risiko    : {risk_level.upper()}\n"
        f"Waktu     : {now_wib}\n"
        f"Confidence: {confidence:.0%}\n"
        f"Shutdown  : {'AKTIF' if shutdown_triggered else 'TIDAK'}\n\n"
        f"Segera periksa area dan ambil tindakan."
    )

    if not fonnte_token:
        print(f"[NOTIFIER] No Fonnte token set. Message would be sent to {phone}:")
        print(message)
        return {"status": "skipped", "reason": "no_token"}

    headers = {"Authorization": fonnte_token}
    data = {
        "target": phone,
        "message": message,
        "countryCode": "62",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post("https://api.fonnte.com/send", headers=headers, data=data)
            result = resp.json()
            print(f"[NOTIFIER] Sent to {phone}: {result}")
            return result
    except Exception as e:
        print(f"[NOTIFIER] Failed to send to {phone}: {e}")
        return {"status": "error", "reason": str(e)}


async def send_to_all_recipients(
    recipients_str: str,
    zone_name: str,
    risk_level: str,
    confidence: float,
    shutdown_triggered: bool,
    facility_name: str,
    fonnte_token: str,
):
    """
    Send WhatsApp to all recipients (comma-separated string).
    """
    if not recipients_str.strip():
        print("[NOTIFIER] No recipients configured.")
        return []

    phones = [p.strip() for p in recipients_str.split(",") if p.strip()]
    tasks = [
        send_whatsapp(phone, zone_name, risk_level, confidence, shutdown_triggered, facility_name, fonnte_token)
        for phone in phones
    ]
    return await asyncio.gather(*tasks)


async def send_test_message(fonnte_token: str, recipients_str: str, facility_name: str) -> list:
    """Send a test WhatsApp message to all recipients."""
    if not recipients_str.strip():
        return [{"status": "error", "reason": "no_recipients"}]

    phones = [p.strip() for p in recipients_str.split(",") if p.strip()]
    now_wib = datetime.now(WIB).strftime("%d/%m/%Y %H:%M:%S WIB")

    message = (
        f"✅ SIEWS+ TEST MESSAGE\n\n"
        f"Fasilitas: {facility_name}\n"
        f"Waktu: {now_wib}\n\n"
        f"Ini adalah pesan uji coba dari sistem SIEWS+ 5.0.\n"
        f"Jika Anda menerima pesan ini, notifikasi WhatsApp berfungsi dengan baik."
    )

    results = []
    for phone in phones:
        if not fonnte_token:
            print(f"[NOTIFIER] Test: No token. Would send to {phone}")
            results.append({"status": "skipped", "reason": "no_token", "phone": phone})
            continue

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.fonnte.com/send",
                    headers={"Authorization": fonnte_token},
                    data={"target": phone, "message": message, "countryCode": "62"},
                )
                results.append({"status": "ok", "phone": phone, "response": resp.json()})
        except Exception as e:
            results.append({"status": "error", "phone": phone, "reason": str(e)})

    return results
