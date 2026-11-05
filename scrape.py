import asyncio, csv, os, re
from urllib.parse import quote
from playwright.async_api import async_playwright

KEYWORD = os.environ.get("KEYWORD", "安踏鞋")
MAX_PAGES = int(os.environ.get("MAX_PAGES", "3"))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def main():
    items, seen = [], set()
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = await b.new_context(locale="zh-CN", user_agent=UA,
            viewport={"width": 1400, "height": 900},
            extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"})
        page = await ctx.new_page()

        for i in range(MAX_PAGES):
            url = f"https://search.jd.com/Search?keyword={quote(KEYWORD)}&enc=utf-8&page={2*i+1}"
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print("goto fail", e); break
            await page.wait_for_timeout(2500)
            title = await page.title()
            if "验证" in title or "抱歉" in title:
                print("BLOCKED:", title); break
            got = await page.evaluate("""() => [...document.querySelectorAll('#J_goodsList .gl-item')]
              .map(e => ({
                sku: e.getAttribute('data-sku'),
                name: (e.querySelector('.p-name em')?.innerText || '').replace(/\\s+/g,' ').trim(),
                price: (e.querySelector('.p-price i')?.innerText || '').trim(),
                shop: (e.querySelector('.p-shop a')?.innerText || '').trim()
              })).filter(x => x.sku && x.name)""")
            print(f"page {2*i+1}: {len(got)} items")
            for x in got:
                if x["sku"] not in seen:
                    seen.add(x["sku"]); items.append(x)
            await page.wait_for_timeout(1500)

        for idx, it in enumerate(items, 1):
            try:
                await page.goto(f"https://item.jd.com/{it['sku']}.html",
                                wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(1000)
                info = await page.evaluate("""() => {
                  const out = {};
                  document.querySelectorAll('.Ptable .Ptable-item').forEach(box => {
                    const dts = [...box.querySelectorAll('dt')];
                    const dds = [...box.querySelectorAll('dd')];
                    dts.forEach((dt, i) => {
                      const k = dt.innerText.replace(/[：:]/g,'').trim();
                      const v = dds[i]?.innerText.trim();
                      if (k && v) out[k] = v;
                    });
                  });
                  const nm = document.querySelector('.sku-name')?.innerText.trim();
                  return {name: nm, ...out};
                }""")
                html = await page.content()
                m = re.search(r'上市时间[^0-9]{0,12}(20\d{2}[年\-\/]\d{1,2}[月\-\/]?\d{0,2})', html)
                if not info.get("上市时间") and m:
                    info["上市时间"] = m.group(1)
                it.update({
                    "商品名": info.get("商品名称") or info.get("name") or it["name"],
                    "上市时间": info.get("上市时间", ""),
                    "货号": info.get("货号", ""),
                    "型号": info.get("型号", ""),
                    "适用": info.get("适用人群", ""),
                    "链接": f"https://item.jd.com/{it['sku']}.html"
                })
                print(idx, it["sku"], it["上市时间"], it["name"][:30])
                await page.wait_for_timeout(700)
            except Exception as e:
                print("detail fail", it["sku"], e)

        os.makedirs("output", exist_ok=True)
        cols = ["sku","商品名","店铺","price","上市时间","货号","型号","适用","链接"]
        with open("output/jd_anta.csv","w",newline="",encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for it in items: w.writerow(it)
        print("TOTAL", len(items))

asyncio.run(main())
