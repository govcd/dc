"""
Dhaka College (DC) Admit Card Checker & Website Generator
==========================================================
Website: https://dhakacollege.eshiksabd.com
Credentials: dcstudent / dcstudent

Features:
  - Checks admit cards for ALL students in a selected batch
  - Downloads sample PDFs to extract exam info (exam name, subject, date, time, center)
  - Saves PDF links for students who got admit cards
  - Generates cumulative JSON data for the website
  - Each run ADDS to the website data (previous runs preserved)

Output:  govcd/dc/admitcard/data/
Website: govcd/dc/admitcard/index.html

Usage:
  python admitcard_checker.py
  (Then select batch interactively)
"""

import sys
import os
import io
import re
import json
import time
import datetime
import requests
import pdfplumber
from pathlib import Path
from playwright.sync_api import sync_playwright

# Fix encoding for Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ══════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════════════════════════════

BASE_URL     = "https://dhakacollege.eshiksabd.com"
COLLEGE_CODE = "dc"
COLLEGE_NAME = "Dhaka College"
FIXED_PREFIX = "120"

BATCH_CONFIGS = {
    "hsc30": {"session": "2829", "label": "HSC-30 (2028-2029)"},
    "hsc29": {"session": "2728", "label": "HSC-29 (2027-2028)"},
    "hsc28": {"session": "2627", "label": "HSC-28 (2026-2027)"},
    "hsc27": {"session": "2526", "label": "HSC-27 (2025-2026)"},
    "hsc26": {"session": "2425", "label": "HSC-26 (2024-2025)"},
    "hsc25": {"session": "2324", "label": "HSC-25 (2023-2024)"},
}

GROUPS = {
    "Science":          {"group_code": "01", "letter": "s", "max_roll": 1100},
    "Business Studies": {"group_code": "02", "letter": "b", "max_roll": 250},
    "Humanities":       {"group_code": "03", "letter": "h", "max_roll": 250},
}

CONSECUTIVE_MISS_CUTOFF = 30   # Stop group after this many consecutive misses

# ══════════════════════════════════════════════════════════════════════
#  PORTAL SESSION (Login & HTTP)
# ══════════════════════════════════════════════════════════════════════

class PortalSession:
    """Handles authentication and HTTP requests to the DC EMS portal."""

    def __init__(self):
        self.session = requests.Session()
        self.user_agent = ""
        self.authenticate()

    def authenticate(self):
        print(f"[*] Authenticating with {COLLEGE_NAME} portal...")
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
            self.user_agent = page.evaluate("navigator.userAgent")
            browser.close()

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent":       self.user_agent,
            "Referer":          f"{BASE_URL}/Basic-Result-Enquiry-Center",
            "Origin":           BASE_URL,
            "X-Requested-With": "XMLHttpRequest",
        })
        for c in cookies:
            self.session.cookies.set(
                c["name"], c["value"],
                domain=c.get("domain"), path=c.get("path", "/")
            )
        print("[+] Authentication successful.\n")

    def post(self, data, timeout=20):
        """POST to controller_student_module.php with auto-reauth."""
        url = f"{BASE_URL}/controller_student_module.php"
        for attempt in range(3):
            try:
                resp = self.session.post(url, data=data, timeout=timeout)
                if "login" in resp.url.lower() or resp.status_code in (401, 403):
                    print("[!] Session expired. Re-authenticating...")
                    self.authenticate()
                    resp = self.session.post(url, data=data, timeout=timeout)
                return resp
            except Exception as e:
                if attempt == 2:
                    raise
                time.sleep(1.5)

    def get(self, url, timeout=25):
        """GET with auto-reauth."""
        for attempt in range(3):
            try:
                resp = self.session.get(url, timeout=timeout)
                if "login" in resp.url.lower() or resp.status_code in (401, 403):
                    self.authenticate()
                    resp = self.session.get(url, timeout=timeout)
                return resp
            except Exception as e:
                if attempt == 2:
                    raise
                time.sleep(1.5)

# ══════════════════════════════════════════════════════════════════════
#  ADMIT CARD CHECK
# ══════════════════════════════════════════════════════════════════════

def check_admit_card(portal, roll_number):
    """
    Check if a student has an admit card.
    Returns (xxCode, "success") or (None, error_message).
    """
    resp = portal.post({"rootData": roll_number, "flagreq": "StudentAdmitCard"})
    text = resp.text.strip()
    if "Error" in text or not text:
        return None, text if text else "empty_response"
    return text, "success"


def download_admit_pdf(portal, xx_code):
    """Download admit card PDF bytes. Returns bytes or None."""
    url = f"{BASE_URL}/Admit-Card?xxCode={xx_code}"
    resp = portal.get(url, timeout=30)
    if resp.status_code == 200:
        pdf_start = resp.content.find(b"%PDF")
        if pdf_start != -1:
            return resp.content[pdf_start:]
    return None


def parse_admit_pdf(pdf_bytes):
    """
    Extract exam info from an admit card PDF.
    Returns dict with: exam_name, subject, exam_date, exam_time, exam_center,
                       student_name, roll, raw_text
    """
    info = {
        "exam_name": "", "subject": "", "exam_date": "", "exam_time": "",
        "exam_center": "", "student_name": "", "roll": "", "raw_text": ""
    }
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if not pdf.pages:
                return info
            text = ""
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
            info["raw_text"] = text

            # ── Student Name ──
            for pat in [
                r"(?:Student\s*Name|Name\s*of\s*Student|Student)\s*[:\-]\s*(.+?)(?:\n|Roll|Class)",
                r"(?:নাম|ছাত্রের নাম)\s*[:\-]\s*(.+?)(?:\n|রোল)",
            ]:
                m = re.search(pat, text, re.I)
                if m:
                    info["student_name"] = m.group(1).strip()
                    break

            # ── Roll Number ──
            for pat in [
                r"(?:Class\s*Roll|Roll\s*No|Roll)\s*[:\-]\s*(\d+)",
                r"(?:রোল\s*নং|রোল)\s*[:\-]\s*(\d+)",
            ]:
                m = re.search(pat, text, re.I)
                if m:
                    info["roll"] = m.group(1).strip()
                    break

            # ── Exam Name ──
            for pat in [
                r"(Class\s*Test[\s\-]*\d+)",
                r"(CT[\s\-]*\d+)",
                r"(Half\s*Yearly\s*(?:Exam(?:ination)?)?)",
                r"(Annual\s*(?:Exam(?:ination)?)?)",
                r"(Model\s*Test[\s\-]*\d*)",
                r"(Pre[\s\-]*Test[\s\-]*\d*)",
                r"(Test\s*Exam(?:ination)?[\s\-]*\d*)",
                r"(?:Exam(?:ination)?\s*Name|পরীক্ষার নাম)\s*[:\-]\s*(.+?)(?:\n|Subject|বিষয়)",
            ]:
                m = re.search(pat, text, re.I)
                if m:
                    info["exam_name"] = (m.group(2) if m.lastindex == 2 else m.group(1)).strip()
                    break

            # ── Subject ──
            for pat in [
                r"(?:Subject|বিষয়)\s*[:\-]\s*(.+?)(?:\n|Date|তারিখ|Time|সময়|Gallery|গ্যালারি)",
                r"(?:Subject\s*Name)\s*[:\-]\s*(.+?)(?:\n)",
            ]:
                m = re.search(pat, text, re.I)
                if m:
                    info["subject"] = m.group(1).strip()
                    break

            # ── Date ──
            for pat in [
                r"(?:Date|তারিখ)\s*[:\-]\s*(.+?)(?:\n|Time|সময়|Day)",
                r"(\d{1,2}[\s/\-]\w+[\s/\-]\d{4})",
                r"(\d{1,2}/\d{1,2}/\d{4})",
            ]:
                m = re.search(pat, text, re.I)
                if m:
                    info["exam_date"] = m.group(1).strip()
                    break

            # ── Time ──
            for pat in [
                r"(?:Time|সময়)\s*[:\-]\s*(.+?)(?:\n|Gallery|Center|Venue|গ্যালারি|কেন্দ্র)",
                r"(\d{1,2}[:.]\d{2}\s*(?:AM|PM|am|pm)\s*(?:to|[-–])\s*\d{1,2}[:.]\d{2}\s*(?:AM|PM|am|pm))",
            ]:
                m = re.search(pat, text, re.I)
                if m:
                    info["exam_time"] = m.group(1).strip()
                    break

            # ── Gallery / Center ──
            for pat in [
                r"(?:Gallery|Center|Venue|Room|Hall|গ্যালারি|কেন্দ্র|ভেন্যু)\s*[:\-]\s*(.+?)(?:\n|$)",
                r"(?:Seat\s*Plan|আসন)\s*[:\-]\s*(.+?)(?:\n|$)",
            ]:
                m = re.search(pat, text, re.I)
                if m:
                    info["exam_center"] = m.group(1).strip()
                    break

    except Exception as e:
        print(f"      [!] PDF parse error: {e}")

    return info

# ══════════════════════════════════════════════════════════════════════
#  LOAD EXISTING STUDENT DATABASE
# ══════════════════════════════════════════════════════════════════════

def load_student_database(batch_key):
    """Load student names from existing batch database (if available)."""
    root = Path(__file__).resolve().parent
    json_path = root / batch_key / "data" / f"{batch_key}.json"

    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                records = json.load(f)
            db = {}
            for r in records:
                roll = r.get("college_roll", "")
                if roll:
                    db[roll] = {
                        "name":       r.get("student_name_en", ""),
                        "group":      r.get("group_name", ""),
                        "short_roll": r.get("short_roll", ""),
                    }
            print(f"[+] Loaded {len(db)} students from existing database ({batch_key})")
            return db
        except Exception as e:
            print(f"[!] Could not load database: {e}")

    print(f"[*] No existing database found for {batch_key}. Will iterate through roll ranges.")
    return {}

# ══════════════════════════════════════════════════════════════════════
#  BATCH CHECK (MAIN LOGIC)
# ══════════════════════════════════════════════════════════════════════

def check_batch(portal, batch_key):
    """Check admit cards for all students in a batch. Returns results dict."""
    cfg = BATCH_CONFIGS.get(batch_key)
    if not cfg:
        print(f"[!] Unknown batch: {batch_key}")
        return None

    session_code = cfg["session"]
    roll_prefix  = f"{FIXED_PREFIX}{session_code}"
    batch_label  = cfg["label"]

    print("=" * 70)
    print(f"   CHECKING ADMIT CARDS: {COLLEGE_NAME.upper()} | {batch_label}")
    print(f"   Roll Prefix: {roll_prefix}")
    print("=" * 70)

    # Load existing student names
    student_db = load_student_database(batch_key)

    results = {
        "with_admit":    [],
        "without_admit": [],
        "exam_info":     {},
    }

    exam_info_collected    = False
    sample_pdfs_downloaded = 0
    MAX_SAMPLES            = 5
    total_found            = 0
    total_not_found        = 0

    # ── Quick pre-check: test first roll to see if admit cards exist at all ──
    test_roll = f"{roll_prefix}010001"
    print(f"\n[*] Quick pre-check with roll {test_roll}...")
    xx_code_test, status_test = check_admit_card(portal, test_roll)
    if xx_code_test:
        print(f"[+] Admit cards are ACTIVE for {batch_label}! Starting full check...\n")
    else:
        print(f"[!] First roll has no admit card (response: {status_test[:80]})")
        print(f"[*] Continuing anyway – some students may still have admit cards...\n")

    for group_name, gcfg in GROUPS.items():
        grp_code = gcfg["group_code"]
        max_roll = gcfg["max_roll"]

        print(f"\n{'─' * 60}")
        print(f"  Group: {group_name} | Rolls: 0001 to {max_roll:04d}")
        print(f"{'─' * 60}")

        consecutive_errors = 0
        group_found        = 0
        group_not_found    = 0

        for num in range(1, max_roll + 1):
            short_roll = str(num).zfill(4)
            full_roll  = f"{roll_prefix}{grp_code}{short_roll}"

            # Student name from database
            db_entry     = student_db.get(full_roll, {})
            student_name = db_entry.get("name", "")

            # ── Check admit card ──
            try:
                xx_code, status = check_admit_card(portal, full_roll)
            except Exception as e:
                print(f"  [!] Network error on {full_roll}: {e}")
                time.sleep(2)
                continue

            if xx_code:
                # ✓ Admit card FOUND
                consecutive_errors = 0
                group_found       += 1
                total_found       += 1

                pdf_url = f"{BASE_URL}/Admit-Card?xxCode={xx_code}"
                entry = {
                    "roll":           full_roll,
                    "short_roll":     short_roll,
                    "group":          group_name,
                    "name":           student_name,
                    "has_admit_card": True,
                    "pdf_link":       pdf_url,
                    "xx_code":        xx_code,
                }
                results["with_admit"].append(entry)

                # ── Download sample PDFs to identify exam ──
                if sample_pdfs_downloaded < MAX_SAMPLES:
                    try:
                        pdf_bytes = download_admit_pdf(portal, xx_code)
                        if pdf_bytes:
                            exam_data = parse_admit_pdf(pdf_bytes)
                            sample_pdfs_downloaded += 1

                            if not exam_info_collected:
                                results["exam_info"] = {
                                    "exam_name":   exam_data.get("exam_name", ""),
                                    "subject":     exam_data.get("subject", ""),
                                    "exam_date":   exam_data.get("exam_date", ""),
                                    "exam_time":   exam_data.get("exam_time", ""),
                                    "exam_center": exam_data.get("exam_center", ""),
                                    "raw_text_sample": exam_data.get("raw_text", "")[:1000],
                                }
                                exam_info_collected = True
                                print(f"\n  ┌── EXAM INFO DETECTED ──────────────────────────")
                                print(f"  │ Exam:    {exam_data.get('exam_name') or '(could not detect)'}")
                                print(f"  │ Subject: {exam_data.get('subject')   or '(could not detect)'}")
                                print(f"  │ Date:    {exam_data.get('exam_date') or '(could not detect)'}")
                                print(f"  │ Time:    {exam_data.get('exam_time') or '(could not detect)'}")
                                print(f"  │ Center:  {exam_data.get('exam_center') or '(could not detect)'}")
                                print(f"  └─────────────────────────────────────────────────\n")
                                # Print raw text for debugging/manual identification
                                raw = exam_data.get('raw_text', '')[:500].replace('\n', '\n  │ ')
                                print(f"  ┌── RAW PDF TEXT (first 500 chars) ──")
                                print(f"  │ {raw}")
                                print(f"  └─────────────────────────────────────────────────\n")
                    except Exception:
                        pass

                # Print progress
                name_disp = student_name[:22] if student_name else "—"
                print(f"  [{short_roll}] {name_disp:<22} -> ✓ ADMIT CARD FOUND")

            else:
                # ✗ No admit card
                consecutive_errors += 1
                group_not_found    += 1
                total_not_found    += 1

                entry = {
                    "roll":       full_roll,
                    "short_roll": short_roll,
                    "group":      group_name,
                    "name":       student_name,
                    "has_admit_card": False,
                }
                results["without_admit"].append(entry)

                # Cutoff: 30 consecutive errors at the end means no more students
                if consecutive_errors >= CONSECUTIVE_MISS_CUTOFF and num > 50:
                    approx_valid = num - CONSECUTIVE_MISS_CUTOFF
                    print(f"  [!] {CONSECUTIVE_MISS_CUTOFF} consecutive misses. Stopping {group_name}. "
                          f"Approx valid rolls: ~{approx_valid}")
                    break

            # Progress every 100 rolls
            if num % 100 == 0:
                print(f"  ... checked {num}/{max_roll} | Found: {group_found} | Not found: {group_not_found}")

            # Gentle rate limiting
            if num % 25 == 0:
                time.sleep(0.3)

        print(f"  [{group_name}] DONE: {group_found} found ✓ | {group_not_found} not found ✗")

    print(f"\n[*] Total: {total_found} with admit card | {total_not_found} without")
    return results

# ══════════════════════════════════════════════════════════════════════
#  SAVE RESULTS & UPDATE WEBSITE DATA
# ══════════════════════════════════════════════════════════════════════

def save_results(batch_key, results, output_dir):
    """Save results to JSON and update cumulative website data file."""
    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    now       = datetime.datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    batch_label = BATCH_CONFIGS.get(batch_key, {}).get("label", batch_key)
    exam_info   = results.get("exam_info", {})

    # ── Build exam record ──
    exam_record = {
        "id":                   f"{batch_key}_{timestamp}",
        "batch":                batch_key,
        "batch_label":          batch_label,
        "exam_name":            exam_info.get("exam_name", ""),
        "subject":              exam_info.get("subject", ""),
        "exam_date":            exam_info.get("exam_date", ""),
        "exam_time":            exam_info.get("exam_time", ""),
        "exam_center":          exam_info.get("exam_center", ""),
        "checked_at":           now.isoformat(),
        "total_with_admit":     len(results["with_admit"]),
        "total_without_admit":  len(results["without_admit"]),
        "total_checked":        len(results["with_admit"]) + len(results["without_admit"]),
        "students_with_admit":  results["with_admit"],
        "students_without_admit": [
            {"roll": s["roll"], "short_roll": s["short_roll"],
             "group": s["group"], "name": s.get("name", "")}
            for s in results["without_admit"]
        ],
        "raw_text_sample":      exam_info.get("raw_text_sample", ""),
    }

    # ── Save individual run file ──
    run_file = data_dir / f"{batch_key}_{timestamp}.json"
    with open(run_file, "w", encoding="utf-8") as f:
        json.dump(exam_record, f, ensure_ascii=False, indent=2)
    print(f"\n[+] Run data saved: {run_file}")

    # ── Update cumulative all_exams.json ──
    cumulative_file = data_dir / "all_exams.json"
    cumulative = {
        "college":      COLLEGE_CODE,
        "college_name": COLLEGE_NAME,
        "last_updated": "",
        "exams":        [],
    }

    if cumulative_file.exists():
        try:
            with open(cumulative_file, "r", encoding="utf-8") as f:
                cumulative = json.load(f)
        except Exception:
            pass

    cumulative["last_updated"] = now.isoformat()
    cumulative["exams"].insert(0, exam_record)   # newest first

    with open(cumulative_file, "w", encoding="utf-8") as f:
        json.dump(cumulative, f, ensure_ascii=False, indent=2)
    print(f"[+] Cumulative data updated: {cumulative_file}")
    print(f"    Total exams tracked: {len(cumulative['exams'])}")

    return exam_record

# ══════════════════════════════════════════════════════════════════════
#  INTERACTIVE MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   DHAKA COLLEGE (DC) - ADMIT CARD CHECKER                  ║")
    print("║   Checks all students' admit cards & generates website     ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    # ── Select batch ──
    batch_keys = list(BATCH_CONFIGS.keys())
    print("  Available batches:")
    for i, key in enumerate(batch_keys, 1):
        print(f"    [{i}] {BATCH_CONFIGS[key]['label']}")
    print()

    choice = input("  Select batch number (default 1): ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(batch_keys):
        batch_key = batch_keys[int(choice) - 1]
    else:
        batch_key = batch_keys[0]

    batch_label = BATCH_CONFIGS[batch_key]["label"]
    print(f"\n  >> Selected: {batch_label}\n")

    # ── Setup output directory ──
    root_dir   = Path(__file__).resolve().parent
    output_dir = root_dir / "admitcard"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "data").mkdir(parents=True, exist_ok=True)

    # ── Authenticate ──
    portal = PortalSession()

    # ── Run admit card check ──
    results = check_batch(portal, batch_key)

    if not results:
        print("[!] No results.")
        return

    # ── Save results ──
    exam_record = save_results(batch_key, results, output_dir)

    # ── Print final summary ──
    exam_name = exam_record.get("exam_name") or "(Auto-detect failed – check raw_text_sample)"
    subject   = exam_record.get("subject")   or "(Auto-detect failed)"

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║                      FINAL SUMMARY                         ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print(f"║  Batch:              {batch_label:<39}║")
    print(f"║  Exam:               {exam_name[:39]:<39}║")
    print(f"║  Subject:            {subject[:39]:<39}║")
    print(f"║  Total Checked:      {exam_record['total_checked']:<39}║")
    print(f"║  Admit Card FOUND:   {exam_record['total_with_admit']:<39}║")
    print(f"║  Admit Card MISSING: {exam_record['total_without_admit']:<39}║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print("║  Data saved to: govcd/dc/admitcard/data/                   ║")
    print("║  Website:       govcd/dc/admitcard/index.html              ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    # ── If exam info could not be auto-detected, ask user ──
    if not exam_record.get("exam_name"):
        print("[?] Exam name could not be auto-detected from the PDF.")
        print("    Raw text from PDF (first 500 chars):")
        raw = exam_record.get("raw_text_sample", "N/A")[:500]
        print(f"    {raw}\n")

        user_exam = input("    Enter exam name (e.g. 'Class Test 2'): ").strip()
        user_subj = input("    Enter subject(s) (e.g. 'Bangla, ICT'): ").strip()

        if user_exam or user_subj:
            # Update the saved files
            data_dir = output_dir / "data"
            cumulative_file = data_dir / "all_exams.json"
            if cumulative_file.exists():
                with open(cumulative_file, "r", encoding="utf-8") as f:
                    cumulative = json.load(f)
                if cumulative["exams"]:
                    cumulative["exams"][0]["exam_name"] = user_exam
                    cumulative["exams"][0]["subject"]   = user_subj
                with open(cumulative_file, "w", encoding="utf-8") as f:
                    json.dump(cumulative, f, ensure_ascii=False, indent=2)
                print(f"\n    [+] Updated exam info: {user_exam} | {user_subj}")

    print("\n[✓] ALL DONE! Run again for next exam/subject.\n")


if __name__ == "__main__":
    main()
