"""Download and parse the HSC-27 admit card PDF to see its format."""
import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright
import requests
import pdfplumber

BASE_URL = "https://dhakacollege.eshiksabd.com"

# 1. Login
print("[1] Logging in...")
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    page.goto(BASE_URL, timeout=45000)
    page.wait_for_load_state("networkidle")
    page.locator("input[name=username]").fill("dcstudent")
    page.locator("input[name=password]").fill("dcstudent")
    page.locator("input[type=submit]").click()
    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(2)
    cookies = context.cookies()
    ua = page.evaluate("navigator.userAgent")
    browser.close()

session = requests.Session()
session.headers.update({
    "User-Agent": ua, "Referer": f"{BASE_URL}/Basic-Result-Enquiry-Center",
    "Origin": BASE_URL, "X-Requested-With": "XMLHttpRequest",
})
for c in cookies:
    session.cookies.set(c["name"], c["value"], domain=c.get("domain"), path=c.get("path", "/"))
print("[+] Login OK\n")

# 2. Get xxCode for HSC-27 roll 1
rolls_to_test = [
    "1202526010001", "1202526010002", "1202526010050",
    "1202526020001", "1202526030001",
]

for roll in rolls_to_test:
    print(f"{'='*60}")
    print(f"  Testing roll: {roll}")
    print(f"{'='*60}")
    
    resp = session.post(f"{BASE_URL}/controller_student_module.php",
                        data={"rootData": roll, "flagreq": "StudentAdmitCard"}, timeout=15)
    text = resp.text.strip()
    
    if "Error" in text:
        print(f"  No admit card: {text[:100]}\n")
        continue
    
    xx_code = text
    pdf_url = f"{BASE_URL}/Admit-Card?xxCode={xx_code}"
    print(f"  xxCode: {xx_code[:60]}...")
    print(f"  PDF URL: {pdf_url[:80]}...")
    
    # Download PDF
    pdf_resp = session.get(pdf_url, timeout=30)
    print(f"  HTTP Status: {pdf_resp.status_code}")
    print(f"  Content-Type: {pdf_resp.headers.get('Content-Type', 'N/A')}")
    print(f"  Content length: {len(pdf_resp.content)} bytes")
    
    # Check if it's a PDF
    pdf_start = pdf_resp.content.find(b"%PDF")
    if pdf_start == -1:
        # Maybe the response is HTML, not PDF
        print(f"  NOT A PDF! Content preview:")
        print(f"  {pdf_resp.text[:500]}")
        print()
        continue
    
    pdf_bytes = pdf_resp.content[pdf_start:]
    print(f"  PDF size: {len(pdf_bytes)} bytes")
    
    # Save PDF for inspection
    save_path = f"c:\\Users\\USER\\Downloads\\##DataScraping\\govcd\\dc\\sample_admitcard_{roll}.pdf"
    with open(save_path, "wb") as f:
        f.write(pdf_bytes)
    print(f"  Saved: {save_path}")
    
    # Parse PDF
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            print(f"  Pages: {len(pdf.pages)}")
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text:
                    print(f"\n  {'='*50}")
                    print(f"  PAGE {i+1} EXTRACTED TEXT:")
                    print(f"  {'='*50}")
                    for line in text.split('\n'):
                        print(f"  | {line}")
                    print(f"  {'='*50}")
                
                # Also try extracting tables
                tables = page.extract_tables()
                if tables:
                    print(f"\n  TABLES on page {i+1}:")
                    for ti, table in enumerate(tables):
                        print(f"    Table {ti+1}:")
                        for row in table:
                            print(f"      {row}")
    except Exception as e:
        print(f"  PDF parse error: {e}")
    
    print()
    # Only do first found admit card for now
    break

print("\n[DONE]")
