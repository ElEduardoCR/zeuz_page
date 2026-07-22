"""Capturas adicionales: paginas de exito/fallo/pendiente con query strings."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUT = Path(__file__).parent.parent / "screenshots"
OUT.mkdir(exist_ok=True)
BASE = "http://localhost:5001"


async def shoot(page, url, name):
    await page.goto(f"{BASE}{url}", wait_until="networkidle")
    await page.wait_for_timeout(300)
    path = OUT / f"{name}.png"
    await page.screenshot(path=str(path), full_page=False)
    print(f"  {name}.png ({path.stat().st_size // 1024} KB)")


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()
        await shoot(page, "/pago/exito?payment_id=123456789&external_reference=ZEUZ-1700000000-ABC123", "08-exito")
        await shoot(page, "/pago/fallo", "09-fallo")
        await shoot(page, "/pago/pendiente", "10-pendiente")
        await shoot(page, "/no-existe-aqui", "11-404")
        await b.close()


asyncio.run(main())
