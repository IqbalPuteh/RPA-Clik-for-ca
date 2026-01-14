from fastapi import FastAPI, HTTPException, status, Request, Depends
import uvicorn, asyncio
from playwright.async_api import async_playwright  
from config import USERNAME, PASSWORD, LOGIN_URL, HEADLESS, BASE_URL
import logging
import time
import os
from fastapi.security.api_key import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from config_helper import load_settings, update_env
from fastapi.responses import HTMLResponse
import sqlite3
from contextlib import closing
from datetime import datetime

# --- GOOGLE DRIVE IMPORTS ---
from google.auth.transport.requests import Request as GoogleRequest  
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- GOOGLE DRIVE CONFIGURATION ---
SHARED_DRIVE_FOLDER_ID = '1qIApzUHagAmouW0Q2p4R9R9Vwyhs8nxq' 
SCOPES = ['https://www.googleapis.com/auth/drive'] 
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.json'

# --- GOOGLE DRIVE AUTHENTICATION FUNCTION ---
async def authenticate_user():
    """Handles the OAuth 2.0 authentication flow."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())  
        else:
            print("Launching browser for initial authentication. Please sign in...")
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
            print(f"Authentication complete. Token saved to {TOKEN_FILE}.")
    return creds

# --- GOOGLE DRIVE UPLOAD FUNCTION ---
async def upload_to_drive(file_path: str, message_id: str):
    credentials = await authenticate_user()
    
    def _do_upload():
        service = build('drive', 'v3', credentials=credentials)
        file_metadata = {
            'name': os.path.basename(file_path),
            'parents': [SHARED_DRIVE_FOLDER_ID]
        }
        media = MediaFileUpload(file_path, mimetype='application/pdf')
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()
        service.permissions().create(
            fileId=file['id'],
            body={'type': 'anyone', 'role': 'reader'},
            supportsAllDrives=True
        ).execute()
        return file['id'], file['webViewLink']

    return await asyncio.to_thread(_do_upload)


app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.post("/")
async def read_root():
    return {"message": "Welcome to RPA Click for FTI Credit Analyst ver. 1.2"}
    
# /get_company parameter class for POST
class CompanyRequest(BaseModel): 
    message_id: str 
    trade_name: str 
    address: str 
    sub_district: str 
    district: str 
    city_code: str
    postal_code: str 
    business_number: str 
    phone: str 

@app.post("/get_company")
async def get_company(req: CompanyRequest) -> str:
    playwright = None
    browser = None
    context = None
    page = None   
    max_retries = 3
    base_delay = 5
    last_error = None
    pdf_filename = None

    for attempt in range(0, max_retries):
        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=False) 
            context = await browser.new_context()
            page = await context.new_page()

            # --- RPA steps (example using req fields) ---
            await page.goto(LOGIN_URL)
            await page.wait_for_load_state("load")
            await page.get_by_role("button", name="").click()
            await page.get_by_role("link", name="English").click()

            await page.wait_for_load_state("load")
            await page.get_by_role("textbox", name="Username").fill(USERNAME)
            await page.get_by_role("textbox", name="Password").fill(PASSWORD)
            await page.get_by_role("button", name="Login").click()

            await page.wait_for_load_state("load")
            await page.get_by_role("link", name="Company").nth(2).click()

            await page.wait_for_load_state("load")
            await page.locator("#CompanyModel_PurposeOfEnquiry").select_option("20")
            await page.locator("#CompanyModel_CompanyDataModel_MessageID").fill(req.message_id)
            await page.locator("#CompanyModel_CompanyDataModel_TradeName").fill(req.trade_name)
            await page.get_by_role("textbox", name="FIELD 'ADDRESS' LENGTH IS NOT").fill(req.address)
            await page.get_by_role("textbox", name="FIELD 'SUB DISTRICT' IS").fill(req.sub_district)
            await page.get_by_role("textbox", name="FIELD 'DISTRICT' IS MANDATORY").fill(req.district)
            await page.locator("#CompanyModel_AddressDataModel_City").select_option(req.city_code)
            await page.get_by_role("textbox", name="FIELD 'POSTAL CODE' IS").fill(req.postal_code)
            await page.locator("#CompanyModel_AddressDataModel_Country").select_option("ID")            
            await page.locator("#CompanyModel_IdentificationCodeModel_BusniessNumber").fill(req.business_number)
            await page.get_by_role("textbox", name="AT LEAST ONE BETWEEN 'PHONE").fill(req.phone)
            await page.get_by_text("Next").click()

            await page.wait_for_load_state("load")
            await page.locator("#ContractModel_IndividualRole").select_option("B")
            await page.locator("#operationCombo").select_option("[[N99,F01],F01]")
            await page.locator("#ContractModel_ContractDataModelCredit_ApplicationAmount").fill("100000000")
            await page.get_by_text("Submit").click()

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            html_filename = f"{req.message_id}_company_{timestamp}.html"

            # --- Save current HTML view ---
            await page.wait_for_load_state("load")
            html_content = await page.content()
            with open(html_filename, "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.info(f"HTML successfully saved locally as: {html_filename}")

            # --- CALL GOOGLE DRIVE UPLOAD ---
            file_id, web_link02 = await upload_to_drive(html_filename, req.message_id)

            # --- Cleanup ---
            if os.path.exists(html_filename):
                os.remove(html_filename)
                logger.info(f"Local file {html_filename} removed.")            

            await page.wait_for_load_state("load")
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            pdf_filename = f"{req.message_id}_company_{timestamp}.pdf"

            # --- PDF Download ---
            page.set_default_timeout(120000)
            async with page.expect_download() as download_info:
                await page.get_by_role("link", name=" View PDF").click()
            
            download = await download_info.value
            await download.save_as(pdf_filename)
            logger.info(f"PDF successfully saved locally as: {pdf_filename}")
            
            # --- CALL GOOGLE DRIVE UPLOAD ---
            file_id, web_link01 = await upload_to_drive(pdf_filename, req.message_id)
            
            # --- Cleanup ---
            if os.path.exists(pdf_filename):
                os.remove(pdf_filename)
                logger.info(f"Local file {pdf_filename} removed.")

            await context.close()
            await browser.close()
            await playwright.stop()

            return f"Company RPA completed successfully on POST methode at attempt #{attempt+1}. Drive Link: {web_link01}. Html Link: {web_link02}"

        except Exception as e:
            last_error = e
            logger.error(f"Attempt {attempt+1} failed: {str(e)}")
            if context:
                await context.close()
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                await asyncio.sleep(delay)

    # If all attempts failed
    logger.error("All retry attempts on Company report failed")
    raise HTTPException(
        status_code=500, 
        detail=f"Company report failed after {max_retries} attempts. Last error: {str(last_error)}"
    )

class IndividualRequest(BaseModel):
    message_id: str
    name: str
    birth_date: str
    gender: str
    address: str
    sub_district: str
    district: str
    city: str
    postal_code: str
    identity_type: str
    id_number: str
    phone_number: str

@app.post("/get_individual")
async def get_individual(req: IndividualRequest) -> str:
    playwright = None
    browser = None
    context = None
    page = None   
    max_retries = 3
    base_delay = 5 
    last_error = None
    pdf_filename = None
    
    for attempt in range(0, max_retries):
        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=HEADLESS)
            context = await browser.new_context()
            page = await context.new_page()
            
            # --- RPA steps ---
            await page.goto(LOGIN_URL)
            await page.wait_for_load_state("load")
            await page.get_by_role("button", name="").click()
            await page.get_by_role("link", name="English").click()
            
            await page.wait_for_load_state("load")
            await page.get_by_role("textbox", name="Username").fill(USERNAME)
            await page.get_by_role("textbox", name="Password").fill(PASSWORD)
            await page.get_by_role("button", name="Login").click()

            await page.wait_for_load_state("load")
            await page.get_by_role("link", name="Individual").first.click()

            await page.wait_for_load_state("load")
            await page.locator("#IndividualModel_PurposeOfEnquiry").select_option("20")
            await page.locator("#IndividualModel_IndividualDataModel_MessageID").fill(req.message_id)
            await page.locator("#IndividualModel_IndividualDataModel_NameAsId").fill(req.name)
            await page.get_by_role("textbox", name="YYYY/MM/DD").fill(req.birth_date)
            await page.get_by_role("textbox", name="YYYY/MM/DD").press("Enter")
            await page.locator("#IndividualModel_IndividualDataModel_GenderCode").select_option(req.gender)
            await page.get_by_role("textbox", name="FIELD 'ADDRESS' LENGTH IS NOT").fill(req.address)
            await page.get_by_role("textbox", name="FIELD 'SUB DISTRICT' IS").fill(req.sub_district)
            await page.get_by_role("textbox", name="FIELD 'DISTRICT' IS MANDATORY").fill(req.district)
            await page.locator("#IndividualModel_AddressDataModel_City").select_option(req.city)
            await page.get_by_role("textbox", name="FIELD 'POSTAL CODE' IS").fill(req.postal_code)
            await page.locator("#IndividualModel_AddressDataModel_Country").select_option("ID")
            await page.locator("#IndividualModel_IdentificationCodeDataModel_Type").select_option(req.identity_type)
            await page.locator("#IndividualModel_IdentificationCodeDataModel_Id").fill(req.id_number)
            await page.locator("#IndividualModel_ContactDataModel_PhoneNumber").fill(req.phone_number)
            await page.get_by_text("Next").click()

            await page.wait_for_load_state("load")
            await page.locator("#ContractModel_IndividualRole").select_option("B")
            await page.locator("#operationCombo").select_option("[[P99,F01],F01]")
            await page.locator("#ContractModel_ContractDataModelCredit_ApplicationAmount").fill("100000000")
            await page.get_by_text("Submit").click()

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            html_filename = f"{req.message_id}_individual_{timestamp}.html"

            # --- Save current HTML view ---
            await page.wait_for_load_state("load")
            html_content = await page.content()
            with open(html_filename, "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.info(f"HTML successfully saved locally as: {html_filename}")

            # --- CALL GOOGLE DRIVE UPLOAD ---
            file_id, web_link02 = await upload_to_drive(html_filename, req.message_id)

            # --- Cleanup ---
            if os.path.exists(html_filename):
                os.remove(html_filename)
                logger.info(f"Local file {html_filename} removed.")             

            await page.wait_for_load_state("load")
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            pdf_filename = f"{req.message_id}_individual_{timestamp}.pdf"

            # --- PDF Download ---
            page.set_default_timeout(120000)
            async with page.expect_download() as download_info:
                await page.get_by_role("link", name=" View PDF").click()
            
            download = await download_info.value
            await download.save_as(pdf_filename)
            logger.info(f"PDF successfully saved locally as: {pdf_filename}")
            
            # --- CALL GOOGLE DRIVE UPLOAD ---
            file_id, web_link01 = await upload_to_drive(pdf_filename, req.message_id)
            
            # --- Cleanup ---
            if os.path.exists(pdf_filename):
                os.remove(pdf_filename)
                logger.info(f"Local file {pdf_filename} removed.")

            await context.close()
            await browser.close()
            await playwright.stop()
            
            logger.info(f"Attempt {attempt+1} succeeded")
            return f"Individual RPA completed successfully on POST method at attempt #{attempt+1}. Drive Link: {web_link01}. Html Link: {web_link02}"

        except Exception as e:
            last_error = e
            logger.error(f"Attempt {attempt+1} failed: {str(e)}")
            
            if page:
                await page.screenshot(path=f"ss-indv-error-attempt{attempt+1}.png")
            if context:
                await context.close()
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()
            
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.info(f"Retrying in {delay} seconds...")
                await asyncio.sleep(delay)
    
    # If all attempts failed
    logger.error("All retry attempts on Individual report failed")
    raise HTTPException(
        status_code=500, 
        detail=f"Individual report failed after {max_retries} attempts. Last error: {str(last_error)}"
    )

# ''' Message ID Database ---
DB_NAME = "reg_data.db"

# --- Pydantic Models ---
class MessageIdRequest(BaseModel):
    submission_id: str

class MessageIdResponse(BaseModel):
    message_id: str
    is_new: bool

# --- Initial Database Setup ---
def init_db():
    with closing(sqlite3.connect(DB_NAME)) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS id_mappings (
                    submission_id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS counter_state (
                    id INTEGER PRIMARY KEY,
                    last_val INTEGER NOT NULL
                )
            """)
            cursor.execute("INSERT OR IGNORE INTO counter_state (id, last_val) VALUES (1, 0)")
            conn.commit()

# --- Core Logic (Changed to POST) ---
@app.post("/generate-id", response_model=MessageIdResponse)
def get_or_create_message_id(request: MessageIdRequest):
    
    clean_submission_id = request.submission_id.strip()
    
    if not clean_submission_id:
        raise HTTPException(status_code=400, detail="Submission ID cannot be empty")

    with closing(sqlite3.connect(DB_NAME)) as conn:
        with closing(conn.cursor()) as cursor:
            
            # 1. CHECK
            cursor.execute("SELECT message_id FROM id_mappings WHERE submission_id = ?", (clean_submission_id,))
            row = cursor.fetchone()
            
            if row:
                return MessageIdResponse(message_id=row[0], is_new=False)
            
            # 2. CREATE
            try:
                cursor.execute("SELECT last_val FROM counter_state WHERE id = 1")
                current_val = cursor.fetchone()[0]
                
                next_val = (current_val % 99999) + 1
                
                counter_string = f"{next_val:05d}"
                now = datetime.now()
                month = now.strftime("%m")
                year = now.strftime("%Y")
                type_code = "FTICLI"
                
                new_message_id = f"{counter_string}{type_code}{month}{year}"
                
                cursor.execute("UPDATE counter_state SET last_val = ? WHERE id = 1", (next_val,))
                cursor.execute("INSERT INTO id_mappings (submission_id, message_id) VALUES (?, ?)", 
                               (clean_submission_id, new_message_id))
                conn.commit()
                
                return MessageIdResponse(message_id=new_message_id, is_new=True)
                
            except Exception as e:
                print(e)
                conn.rollback()
                raise HTTPException(status_code=500, detail=str(e))


# ---  API-Key Security ---
API_KEY = "supersecret098"
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME)

def require_api_key(key: str = Depends(api_key_header)):
    if key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API Key"
        )

# --- Schema for Validation ---
class ConfigModel(BaseModel):
    LOGIN_URL: str
    USERNAME: str
    PASSWORD: str
    BASE_URL: str
    HEADLESS: bool

# --- FastAPI App Setup ---
templates = Jinja2Templates(directory="templates")

@app.get(
    "/config",
    response_model=ConfigModel,
)
def get_config():
    # Initialize DB on startup
    init_db()
    return load_settings()

@app.put(
    "/config",
    response_model=ConfigModel,
)
def put_config(cfg: ConfigModel):
    update_env(cfg.dict())
    return cfg

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    cfg = load_settings()
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "config": cfg
    })

@app.get("/db/counter-state/all")
def get_counter_state_all():
    """
    Get all fields and values from counter_state table.
    """
    try:
        with closing(sqlite3.connect(DB_NAME)) as conn:
            conn.row_factory = sqlite3.Row
            with closing(conn.cursor()) as cursor:
                cursor.execute("SELECT * FROM counter_state where id = 1")
                rows = cursor.fetchall()
                
                if not rows:
                    raise HTTPException(
                        status_code=404, 
                        detail="counter_state table is empty"
                    )
                
                # Get column names
                cursor.execute("PRAGMA table_info(counter_state)")
                columns = [col[1] for col in cursor.fetchall()]
                
                result = {
                    "table": "counter_state",
                    "columns": columns,
                    "data": [dict(row) for row in rows],
                    "total_rows": len(rows),
                    "timestamp": datetime.now().isoformat()
                }
                
                return result
                
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import Query

# Pydantic models for structured responses
class IdMappingRecord(BaseModel):
    submission_id: str
    message_id: str
    created_at: str

class IdMappingsResponse(BaseModel):
    table_name: str
    total_records: int
    returned_records: int
    columns: List[str]
    data: List[Dict[str, Any]]
    timestamp: str

class PaginatedIdMappingsResponse(BaseModel):
    table_name: str
    columns: List[str]
    data: List[IdMappingRecord]
    pagination: Dict[str, Any]
    timestamp: str

# GET endpoint to view ALL id_mappings data (no pagination)
@app.get("/db/id-mappings/all", response_model=IdMappingsResponse)
def get_all_id_mappings():
    """
    Get ALL records from id_mappings table with all fields.
    Warning: This might return large amounts of data.
    """
    try:
        with closing(sqlite3.connect(DB_NAME)) as conn:
            conn.row_factory = sqlite3.Row  # Enable dict-like access
            with closing(conn.cursor()) as cursor:
                
                # Get all columns/fields from the table
                cursor.execute("PRAGMA table_info(id_mappings)")
                columns_info = cursor.fetchall()
                columns = [col[1] for col in columns_info]
                
                # Get total count
                cursor.execute("SELECT COUNT(*) FROM id_mappings")
                total_records = cursor.fetchone()[0]
                
                # Get ALL data
                cursor.execute("SELECT * FROM id_mappings ORDER BY created_at DESC")
                rows = cursor.fetchall()
                
                # Convert rows to list of dictionaries
                data = []
                for row in rows:
                    row_dict = {}
                    for i, col_name in enumerate(columns):
                        row_dict[col_name] = row[i]
                    data.append(row_dict)
                
                return IdMappingsResponse(
                    table_name="id_mappings",
                    total_records=total_records,
                    returned_records=len(data),
                    columns=columns,
                    data=data,
                    timestamp=datetime.now().isoformat()
                )
                
    except sqlite3.Error as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Database error: {str(e)}"
        )


if __name__ == "__main__":
    uvicorn.run(
        "new-main:app",        
        host="0.0.0.0",
        port=8000,
        reload=True
    )