"""Toma capturas de las paginas clave de la tienda para revision visual."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUT = Path(__file__).parent.parent / "screenshots"
OUT.mkdir(exist_ok=True)
BASE = "http://localhost:5001"


async def shoot(page, url, name, viewport=(1280, 900), full_page=True, setup=None):
    await page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    if setup:
        await setup(page)
    await page.goto(f"{BASE}{url}", wait_until="networkidle")
    await page.wait_for_timeout(400)
    path = OUT / f"{name}.png"
    await page.screenshot(path=str(path), full_page=full_page)
    print(f"  {name}.png  ({path.stat().st_size // 1024} KB)")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context()
        page = await ctx.new_page()

        # Landing
        await shoot(page, "/", "01-landing")

        # Catalogo
        await shoot(page, "/catalogo", "02-catalogo")

        # Producto
        await shoot(page, "/producto/zeuzdnc-device", "03-producto")

        # Carrito vacio
        await shoot(page, "/carrito", "04-carrito-vacio")

        # Carrito con productos (simulando localStorage)
        async def add_to_cart(p):
            await p.evaluate("""() => {
                localStorage.setItem('zeuz_dnc_cart_v1', JSON.stringify({
                    items: { 'zeuzdnc-device': 1, 'rs232-adapter': 2, 'cable-db9': 1 }
                }));
            }""")

        await shoot(page, "/carrito", "05-carrito-lleno", setup=add_to_cart)

        # Checkout
        await shoot(page, "/checkout", "06-checkout", setup=add_to_cart)

        # Movil (landing)
        await shoot(page, "/", "07-landing-movil", viewport=(390, 800))

        await browser.close()
    print(f"\nCapturas guardadas en: {OUT}")


asyncio.run(main())
