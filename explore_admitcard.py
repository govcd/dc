"""
Explore DC EMS Portal - Admit Card tab specifically.
Click the Admit Card button and capture all API calls.
"""

import json
import time
import sys
import io
from playwright.sync_api import sync_playwright

# Fix encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE_URL = "https://dhakacollege.eshiksabd.com"

def explore_admit_card():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        
        # Capture ALL network requests/responses
        captured = []
        
        def on_response(response):
            url = response.url
            try:
                body = response.text()
            except:
                body = "[binary]"
            captured.append({
                "url": url,
                "status": response.status,
                "body_preview": body[:2000] if body else ""
            })
            if "controller" in url or "admit" in url.lower():
                print(f"\n[NETWORK] {response.status} {url}")
                print(f"  Body: {body[:1000]}")
        
        page = context.new_page()
        page.on("response", on_response)
        
        # Step 1: Login
        print("=" * 70)
        print("  STEP 1: Login")
        print("=" * 70)
        page.goto(BASE_URL, timeout=45000)
        page.wait_for_load_state("networkidle")
        page.locator("input[name=username]").fill("dcstudent")
        page.locator("input[name=password]").fill("dcstudent")
        page.locator("input[type=submit]").click()
        page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(2)
        print(f"[+] Logged in. URL: {page.url}")
        
        # Step 2: Get the openStudent JS function source
        print("\n" + "=" * 70)
        print("  STEP 2: Get openStudent JS function")
        print("=" * 70)
        
        js_source = page.evaluate("""() => {
            if (typeof openStudent === 'function') {
                return openStudent.toString();
            }
            // Also search all scripts
            const scripts = document.querySelectorAll('script');
            let found = '';
            scripts.forEach(s => {
                if (s.textContent && s.textContent.includes('openStudent')) {
                    found += s.textContent;
                }
            });
            return found.substring(0, 5000);
        }""")
        print(f"openStudent function:\n{js_source[:3000]}")
        
        # Step 3: Click "Admit Card" button
        print("\n" + "=" * 70)
        print("  STEP 3: Click Admit Card button")
        print("=" * 70)
        
        captured.clear()  # Clear to capture only admit card related requests
        
        # Click the Admit Card button
        admit_btn = page.locator("button", has_text="Admit Card")
        if admit_btn.count() > 0:
            print(f"Found Admit Card button, clicking...")
            admit_btn.first.click()
            time.sleep(3)
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(2)
            
            # Screenshot the admit card tab
            page.screenshot(path="c:\\Users\\USER\\Downloads\\##DataScraping\\govcd\\dc\\admit_card_tab.png", full_page=True)
            print("[+] Screenshot saved: admit_card_tab.png")
            
            # Get the content of the admit card tab/panel
            admit_content = page.evaluate("""() => {
                // Try to find the admitCard panel
                const panel = document.getElementById('admitCard');
                if (panel) return panel.innerHTML.substring(0, 10000);
                
                // Try active tab
                const active = document.querySelector('.tabcontent[style*="display: block"]') || 
                               document.querySelector('.tab-pane.active') ||
                               document.querySelector('[id="admitCard"]');
                if (active) return active.innerHTML.substring(0, 10000);
                
                return document.body.innerHTML.substring(0, 10000);
            }""")
            print(f"\nAdmit Card panel HTML:\n{admit_content[:5000]}")
            
            # Save full panel HTML
            with open("c:\\Users\\USER\\Downloads\\##DataScraping\\govcd\\dc\\admit_card_panel.html", "w", encoding="utf-8") as f:
                f.write(admit_content)
            
            # Look for form elements, inputs, selects in the admit card panel
            form_elements = page.evaluate("""() => {
                const panel = document.getElementById('admitCard') || document.body;
                const inputs = panel.querySelectorAll('input, select, button, textarea');
                return Array.from(inputs).map(el => ({
                    tag: el.tagName,
                    type: el.type || '',
                    name: el.name || '',
                    id: el.id || '',
                    value: el.value || '',
                    placeholder: el.placeholder || '',
                    text: el.textContent ? el.textContent.trim().substring(0, 100) : '',
                    className: el.className.substring(0, 100),
                    options: el.tagName === 'SELECT' ? Array.from(el.options).map(o => ({value: o.value, text: o.text.substring(0, 80)})) : []
                }));
            }""")
            
            print(f"\nForm elements in Admit Card panel ({len(form_elements)}):")
            for el in form_elements:
                print(f"  {el['tag']} | name={el['name']} | id={el['id']} | type={el['type']} | placeholder={el['placeholder']}")
                if el['options']:
                    for opt in el['options'][:20]:
                        print(f"    option: value={opt['value']} text={opt['text']}")
        
        # Step 4: Try entering a roll number if there's an input field
        print("\n" + "=" * 70)
        print("  STEP 4: Try entering a roll number")
        print("=" * 70)
        
        # Look for roll input in admitCard panel
        roll_input = page.evaluate("""() => {
            const panel = document.getElementById('admitCard') || document.body;
            const inputs = panel.querySelectorAll('input[type="text"], input[type="number"], input:not([type])');
            return Array.from(inputs).map(el => ({
                name: el.name || '',
                id: el.id || '',
                placeholder: el.placeholder || '',
                className: el.className
            }));
        }""")
        print(f"Roll input fields: {json.dumps(roll_input, indent=2)}")
        
        # Try to find any submit/check button in the admit card panel
        buttons_in_panel = page.evaluate("""() => {
            const panel = document.getElementById('admitCard') || document.body;
            const btns = panel.querySelectorAll('button, input[type="submit"], input[type="button"], a.btn');
            return Array.from(btns).map(el => ({
                tag: el.tagName,
                text: el.textContent.trim().substring(0, 100),
                id: el.id || '',
                name: el.name || '',
                onclick: el.getAttribute('onclick') || '',
                className: el.className.substring(0, 100)
            }));
        }""")
        print(f"\nButtons in panel: {json.dumps(buttons_in_panel, indent=2)}")
        
        # Step 5: Look for ALL JS functions related to admit card
        print("\n" + "=" * 70)
        print("  STEP 5: All JS related to admit cards")
        print("=" * 70)
        
        all_js = page.evaluate("""() => {
            const scripts = document.querySelectorAll('script');
            let all = '';
            scripts.forEach(s => { all += s.textContent + '\\n'; });
            // Find lines with admit
            const lines = all.split('\\n');
            const relevant = [];
            for (let i = 0; i < lines.length; i++) {
                const l = lines[i].toLowerCase();
                if (l.includes('admit') || l.includes('admitcard') || l.includes('admit_card')) {
                    // Include surrounding context
                    for (let j = Math.max(0, i-2); j <= Math.min(lines.length-1, i+5); j++) {
                        relevant.push(lines[j]);
                    }
                    relevant.push('---');
                }
            }
            return relevant.join('\\n').substring(0, 8000);
        }""")
        print(f"Admit-related JS:\n{all_js}")
        
        # Step 6: Try with a known roll number
        print("\n" + "=" * 70)
        print("  STEP 6: Try with a known roll for HSC-28")
        print("=" * 70)
        
        # HSC-28 Science roll 1: 12026270101001
        test_roll = "120262701001"
        captured.clear()
        
        # Try the admitCardCheck flagreq
        try:
            result = page.evaluate(f"""() => {{
                return new Promise((resolve, reject) => {{
                    const xhr = new XMLHttpRequest();
                    xhr.open('POST', '{BASE_URL}/controller_student_module.php', true);
                    xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
                    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                    xhr.onload = function() {{
                        resolve({{status: xhr.status, text: xhr.responseText.substring(0, 3000)}});
                    }};
                    xhr.onerror = function() {{ reject('XHR error'); }};
                    xhr.send('rootData={test_roll}&flagreq=admitCardCheck');
                }});
            }})""")
            print(f"admitCardCheck response: {json.dumps(result, indent=2)}")
        except Exception as e:
            print(f"admitCardCheck error: {e}")
        
        # Try other possible flagreq values
        for flagreq in ["admitCard", "getAdmitCard", "checkAdmitCard", "admitCardPrint", "printAdmitCard", "admitCardData"]:
            try:
                result = page.evaluate(f"""() => {{
                    return new Promise((resolve, reject) => {{
                        const xhr = new XMLHttpRequest();
                        xhr.open('POST', '{BASE_URL}/controller_student_module.php', true);
                        xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
                        xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                        xhr.onload = function() {{
                            resolve({{status: xhr.status, text: xhr.responseText.substring(0, 1000)}});
                        }};
                        xhr.onerror = function() {{ reject('error'); }};
                        xhr.send('rootData={test_roll}&flagreq={flagreq}');
                    }});
                }})""")
                if result.get('text', '').strip():
                    print(f"\nflagreq='{flagreq}' -> status={result['status']}, response: {result['text'][:500]}")
            except Exception as e:
                print(f"flagreq='{flagreq}' -> error: {e}")
        
        # Network requests captured
        print("\n" + "=" * 70)
        print("  CAPTURED REQUESTS (after admit card click)")
        print("=" * 70)
        for req in captured:
            if "controller" in req['url'] or req['status'] != 200:
                print(f"  [{req['status']}] {req['url']}")
                if req['body_preview']:
                    print(f"    {req['body_preview'][:500]}")
        
        browser.close()
        print("\n[DONE]")

if __name__ == "__main__":
    explore_admit_card()
