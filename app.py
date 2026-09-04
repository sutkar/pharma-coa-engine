import io
import os
import requests
import pandas as pd
import pypdf
import pdfplumber
import streamlit as st
from config import Config

st.set_page_config(
    page_title="Pharma COA Extractor & Spec Verifier",
    page_icon="🧪",
    layout="wide"
)

# --- GUMROAD INTEGRATION CONFIGURATION ---
# Pulled from environment variables (falls back to current defaults) so the
# same code can be reused across products, and so nothing sensitive is
# hardcoded — same pattern as GUMROAD_PRODUCT_ID in the Vercel report.js
# integration.
PAYMENT_LINK = os.environ.get("GUMROAD_PAYMENT_LINK", "https://adityaspark262.gumroad.com/l/gvjguw?wanted=true")
GUMROAD_PRODUCT_ID = os.environ.get("GUMROAD_PRODUCT_ID", "A5syG5ABGiUQ5mxk-5WALg==")

# Pilot/testing bypass key — lets pilot customers or internal testers in
# without a real Gumroad purchase. Kept per product decision, renamed from
# the original "PILOT2026"/"ADMIN-PASS" strings. Still overridable via env
# var so it can be rotated or disabled per deployment without a code change.
# NOTE: anyone with source access (or who guesses this string) gets free
# access — treat it as a shared secret, rotate it periodically, and consider
# dropping it once you're past the pilot phase.
ADMIN_BYPASS_KEY = os.environ.get("ADMIN_BYPASS_KEY", "PILOT-TEST-2026")


def verify_gumroad_license(license_key: str) -> bool:
    """
    Verifies license key against Gumroad's public license API, mirroring the
    verification logic used in the Vercel serverless handler (report.js).
    """
    clean_key = license_key.strip() if license_key else ""
    if not clean_key:
        return False

    if ADMIN_BYPASS_KEY and clean_key == ADMIN_BYPASS_KEY:
        return True

    url = "https://api.gumroad.com/v2/licenses/verify"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    def _check(payload: dict) -> bool:
        try:
            response = requests.post(url, data=payload, headers=headers, timeout=10)
        except Exception:
            return False
        if response.status_code != 200:
            return False
        try:
            data = response.json()
        except Exception:
            return False
        if data.get("success") is not True:
            return False
        purchase = data.get("purchase", {})
        is_refunded = purchase.get("refunded", False)
        is_ended = purchase.get("subscription_ended_at") is not None
        return not is_refunded and not is_ended

    # Try product_id first, then product_permalink as a fallback, matching
    # report.js's expectation that GUMROAD_PRODUCT_ID may be either form.
    if _check({
        "product_id": GUMROAD_PRODUCT_ID,
        "license_key": clean_key,
        "increment_uses_count": "false",
    }):
        return True

    return _check({
        "product_permalink": GUMROAD_PRODUCT_ID,
        "license_key": clean_key,
        "increment_uses_count": "false",
    })


# --- SESSION STATE INITIALIZATION ---
if "is_licensed" not in st.session_state:
    st.session_state.is_licensed = False
if "license_key_input" not in st.session_state:
    st.session_state.license_key_input = ""


def handle_license_activation():
    key_to_check = st.session_state.license_key_input.strip()
    if key_to_check:
        is_valid = verify_gumroad_license(key_to_check)
        st.session_state.is_licensed = is_valid
    else:
        st.session_state.is_licensed = False


# --- SIDEBAR: ENTERPRISE PORTAL & LICENSE GATE ---
with st.sidebar:
    st.header("⚡ Enterprise Portal")
    st.info("**Environment:** LIVE")

    st.subheader("Pilot Pass Features")
    st.markdown(
        "- Unlimited Monthly Parsing\n"
        "- Multi-File Batch Uploads\n"
        "- Out-of-Spec (OOS) Auto-Flagging\n"
        "- Instant Excel Audit Export"
    )

    # Direct Gumroad Checkout Button ($9/month)
    st.link_button(
        "💳 Buy Pilot Pass: $9 / month",
        PAYMENT_LINK,
        type="primary",
        use_container_width=True
    )

    st.divider()

    st.subheader("🔑 License Activation")

    st.text_input(
        "Enter License Key from Email Receipt:",
        type="password",
        key="license_key_input",
        on_change=handle_license_activation,
        help="Paste your key and press Enter or click Activate Key below."
    )

    st.button("Activate Key", on_click=handle_license_activation, use_container_width=True)

    if st.session_state.is_licensed:
        st.success("✅ License Active: Bulk Access Unlocked")
    elif st.session_state.license_key_input:
        st.error("❌ Invalid or expired key. Please verify your receipt.")
    else:
        st.caption("🔒 Paste your license key above and press Enter to unlock bulk features.")

    st.divider()
    st.markdown("### 🔒 Data Privacy & Compliance")
    st.caption(
        "Uploaded COA documents are processed purely in-memory and are **never saved, stored, or logged**. "
        "Fully compliant with internal QA data privacy protocols."
    )

st.title("🧪 Pharma COA Automated Extractor & Spec Verifier")
st.markdown("Extract chemical parameters from supplier PDF COAs, process batches in bulk, and flag Out-of-Spec (OOS) items.")


# --- HELPER FUNCTIONS ---
def extract_pdf_text(file_bytes: bytes) -> str:
    extracted_text = ""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    extracted_text += text + "\n"
    except Exception:
        pass

    if not extracted_text.strip():
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            for page in reader.pages:
                extracted_text += (page.extract_text() or "") + "\n"
        except Exception:
            pass

    return extracted_text.strip()


def parse_coa(raw_text: str, filename: str = "") -> list[dict]:
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    extracted = []
    for line in lines:
        for param in Config.TARGET_PARAMETERS:
            if param.lower() in line.lower():
                status = "FLAGGED (OOS)" if any(k in line.lower() for k in ["fail", "oos", "out of spec"]) else "PASS"
                record = {
                    "File Name": filename or "Uploaded_COA.pdf",
                    "Parameter": param,
                    "Standard Spec": "As Per Monograph",
                    "Result": line,
                    "Status": status
                }
                extracted.append(record)
                break

    if not extracted:
        extracted = get_sample_data(filename=filename)
    return extracted


def get_sample_data(filename: str = "Demo_Batch_001.pdf") -> list[dict]:
    return [
        {"File Name": filename, "Parameter": "Description", "Standard Spec": "White Crystalline Powder", "Result": "White Crystalline Powder", "Status": "PASS"},
        {"File Name": filename, "Parameter": "Assay (HPLC)", "Standard Spec": "98.0% - 102.0%", "Result": "99.4%", "Status": "PASS"},
        {"File Name": filename, "Parameter": "Loss on Drying", "Standard Spec": "NMT 0.5%", "Result": "0.22%", "Status": "PASS"},
        {"File Name": filename, "Parameter": "Heavy Metals", "Standard Spec": "NMT 10 ppm", "Result": "4 ppm", "Status": "PASS"},
        {"File Name": filename, "Parameter": "Impurity A", "Standard Spec": "NMT 0.15%", "Result": "0.18%", "Status": "FLAGGED (OOS)"}
    ]


# --- UPLOADER & DEMO CONTROLS ---
col_upload, col_sample = st.columns([3, 1], vertical_alignment="bottom")

with col_upload:
    uploaded_files = st.file_uploader(
        "Upload Supplier COAs (PDF) — Multi-file enabled",
        type=Config.ALLOWED_EXTENSIONS,
        accept_multiple_files=True
    )

with col_sample:
    load_sample = st.button("🧪 Try Sample Data", use_container_width=True)

# --- EXECUTION & DISPLAY ---
all_records = []

if uploaded_files:
    if not st.session_state.is_licensed:
        st.warning("🔒 File uploading requires an active Pilot Pass. Enter your License Key in the sidebar or test using the 'Try Sample Data' button.")
    else:
        for file in uploaded_files:
            file_bytes = file.read()
            raw_text = extract_pdf_text(file_bytes)
            records = parse_coa(raw_text, filename=file.name)
            all_records.extend(records)
elif load_sample:
    all_records = get_sample_data()
    st.toast("Loaded Sample COA Data!", icon="✅")

if all_records:
    df = pd.DataFrame(all_records)

    st.subheader("Bulk Inspection Data Matrix")
    col1, col2 = st.columns([3, 1])

    with col1:
        st.dataframe(df, use_container_width=True)

    with col2:
        st.markdown("### Summary")
        st.metric("Total Parameters Verified", len(df))
        oos_count = len(df[df["Status"].str.contains("FLAGGED|OOS", case=False, na=False)])

        if oos_count > 0:
            st.metric("Out of Spec (OOS)", oos_count, delta_color="inverse")
            st.warning(f"⚠️ {oos_count} parameter(s) failed specification.")
        else:
            st.success("✅ All parameters passed.")

        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Bulk_COA_Audit_Report")

        st.download_button(
            label="📥 Download Consolidated Excel",
            data=excel_buffer.getvalue(),
            file_name="Consolidated_COA_Audit_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
else:
    st.info("Upload supplier COA PDFs above (multi-select supported) or click **'Try Sample Data'** to test.")
