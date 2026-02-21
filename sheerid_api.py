"""
SheerID API Integration Module
Core verification logic (Updated with Reference Bot Logic + Session Warming)
"""
import re
import json
import time
import base64
from urllib.parse import urlparse, parse_qs
from curl_cffi import requests
import anti_detect

class SheerIDClient:
    def __init__(self, proxy=None):
        self.session, _, _ = anti_detect.create_session(proxy=proxy)
        self.base_url = "https://services.sheerid.com/rest/v2"
        
    def extract_verification_id_from_url(self, url):
        """Extracts verificationId or ProgramId from a SheerID URL"""
        match = re.search(r'verificationId=([a-zA-Z0-9]{24})', url)
        if match:
             return match.group(1), False # (ID, IsProgramID)
             
        match = re.search(r'/verify/([a-zA-Z0-9]{24})', url)
        if match:
            return match.group(1), True # Assume Program ID if not in query
            
        return None, False

    def start_verification(self, program_id):
        """Creates a new verification session for a program"""
        print(f"[*] Initializing new verification session for program {program_id}...")
        url = f"{self.base_url}/verification"
        payload = {
            "programId": program_id,
            "metadata": {
                "locale": "en-US",
                "marketConsentValue": False
            }
        }
        try:
            resp = self.session.post(url, json=payload, headers=anti_detect.get_headers())
            data = resp.json()
            vid = data.get("verificationId")
            if vid:
                print(f"[*] New Verification ID created: {vid}")
                return vid
            else:
                print(f"[!] Failed to create session: {data}")
                return None
        except Exception as e:
            print(f"[!] Error starting verification: {e}")
            return None

    def get_verification_details(self, verification_id):
        """Get current status of verification"""
        url = f"{self.base_url}/verification/{verification_id}"
        resp = self.session.get(url, headers=anti_detect.get_headers())
        if resp.status_code != 200:
            print(f"[!] Error getting details ({resp.status_code}): {resp.text}")
        return resp.json()

    def submit_student_info(self, verification_id, student_data):
        """Step 1: Submit personal info (With Advanced Metadata)"""
        url = f"{self.base_url}/verification/{verification_id}/step/collectStudentPersonalInfo"
        
        payload = {
            "firstName": student_data["firstName"],
            "lastName": student_data["lastName"],
            "birthDate": student_data["birthDate"],
            "email": student_data["email"],
            "phoneNumber": "",
            "organization": {
                "id": student_data["organization"]["id"],
                "idExtended": str(student_data["organization"]["id"]),
                "name": student_data["organization"]["name"]
            },
            "deviceFingerprintHash": anti_detect.get_fingerprint(),
            "locale": "en-US",
            "metadata": {
                "marketConsentValue": False,
                "verificationId": verification_id,
                "refererUrl": f"https://services.sheerid.com/verify/67c8c14f5f17a83b745e3f82/?verificationId={verification_id}",
                "flags": '{"collect-info-step-email-first":"default","doc-upload-considerations":"default","doc-upload-may24":"default","doc-upload-redesign-use-legacy-message-keys":false,"docUpload-assertion-checklist":"default","font-size":"default","include-cvec-field-france-student":"not-labeled-optional"}',
                "submissionOptIn": "By submitting the personal information above, I acknowledge that my personal information is being collected under the privacy policy of the business from which I am seeking a discount"
            }
        }
        
        headers = anti_detect.get_headers()
        headers["Referer"] = f"https://services.sheerid.com/verify/67c8c14f5f17a83b745e3f82/?verificationId={verification_id}"
        headers["Origin"] = "https://services.sheerid.com"
        
        resp = self.session.post(
            url, 
            json=payload, 
            headers=headers
        )
        if resp.status_code != 200:
            print(f"[!] Submit Info Error ({resp.status_code}): {resp.text}")
            
        return resp.json()

    def skip_sso(self, verification_id):
        """Step 3 (Optional): Bypass SSO Step"""
        url = f"{self.base_url}/verification/{verification_id}/step/sso"
        print(f"[*] Attempting SSO Bypass for {verification_id}...")
        try:
             resp = self.session.delete(url, headers=anti_detect.get_headers())
             return resp.json()
        except:
             return {"currentStep": "sso_skip_failed"}

    def upload_document(self, verification_id, doc_bytes, doc_type="student_id"):
        """Step 2: Upload document if required"""
        url = f"{self.base_url}/verification/{verification_id}/step/docUpload"
        
        # 1. Initiate upload to get URL
        init_payload = {
            "files": [
                {"fileName": "student_id.png", "mimeType": "image/png", "fileSize": len(doc_bytes)}
            ]
        }
        headers = anti_detect.get_headers()
        headers["Referer"] = f"https://services.sheerid.com/verify/67c8c14f5f17a83b745e3f82/?verificationId={verification_id}"
        
        resp = self.session.post(url, json=init_payload, headers=headers)
        data = resp.json()
        
        if not data.get("documents"):
            return {"status": "UPLOAD_INIT_FAILED", "details": data}
            
        upload_url = data["documents"][0]["uploadUrl"]
        
        # 2. Put to S3 (no sheerid headers here)
        s3_headers = {"Content-Type": "image/png"}
        self.session.put(upload_url, data=doc_bytes, headers=s3_headers)
        
        # 3. Complete
        anti_detect.random_delay(1000, 2000)
        complete_url = f"{self.base_url}/verification/{verification_id}/step/completeDocUpload"
        final_resp = self.session.post(complete_url, headers=anti_detect.get_headers())
        
        return final_resp.json()

    def check_status(self, verification_id, max_polling=20):
        """Poll for final status with extended timeout"""
        print(f"[*] Polling status for {verification_id}...")
        
        for i in range(max_polling):
            try:
                details = self.get_verification_details(verification_id)
                step = details.get("currentStep")
                
                print(f"    [{i+1}/{max_polling}] Status: {step}")
                
                if step == "success":
                    reward = details.get("rewardCode")
                    redirect_url = details.get("redirectUrl")
                    if not redirect_url and details.get("metadata"):
                        redirect_url = details.get("metadata").get("redirectUrl")
                        
                    return {
                        "status": "SUCCESS", 
                        "reward_code": reward,
                        "redirect_url": redirect_url,
                        "full_details": details
                    }
                    
                elif step == "error" or details.get("errorIds"):
                     errors = details.get("errorIds", [])
                     if "fraudRulesReject" in errors:
                         return {"status": "FRAUD_REJECT", "errors": errors}
                     return {"status": "FAILED", "reason": errors}
                
                elif step == "docUpload":
                     return {"status": "DOC_UPLOAD_REQUIRED", "details": details}
                     
                elif step == "sso":
                     # If stuck on SSO, try to skip again
                     self.skip_sso(verification_id)
                     
                time.sleep(2)
            except:
                time.sleep(2)
            
        return {"status": "TIMEOUT", "last_details": details}

    def process_verification(self, input_id, is_program_id, student_data, doc_generator_func=None):
        """Full automated flow with Deep Bypass & Auto-Regeneration"""
        # --- DEEP BYPASS: Always Force CLEAN Session ---
        program_id = "67c8c14f5f17a83b745e3f82" # Default Gemini
        
        # Force regenerate a new ID regardless of what the user sent
        # This bypasses tainted sessions from mobile/wrong IPs
        verification_id = self.start_verification(program_id)
        
        if not verification_id:
            verification_id = input_id

        print(f"[*] DEEP BYPASS INITIATED: Fresh Session {verification_id}")
        
        # Session Warming
        landing_url = f"https://services.sheerid.com/verify/{program_id}/?verificationId={verification_id}"
        try:
             self.session.get(landing_url, headers=anti_detect.get_headers(for_sheerid=False))
             anti_detect.random_delay(1500, 3000)
        except: pass

        # Submit Info
        print(f"[*] Submitting Payload: {student_data['display_info']['full_name']}")
        result = self.submit_student_info(verification_id, student_data)
        current_step = result.get("currentStep")
        
        # Handle Instant Error
        if current_step == "error" or not current_step:
            print("[!] Step 1 returned error. Checking actual state...")
            details = self.get_verification_details(verification_id)
            current_step = details.get("currentStep")
            print(f"[*] Current status from API: {current_step}")
        
        # 2. Skip SSO if prompted
        if current_step == "sso":
             print("[*] SSO Step detected. Bypassing...")
             result = self.skip_sso(verification_id)
             current_step = result.get("currentStep")
             print(f"[*] Step 2 (SSO Bypass) Result: {current_step}")
        
        if current_step == "success":
            return self.check_status(verification_id)
            
        elif current_step == "docUpload":
            print("[*] Document upload required. Generating fake doc...")
            if doc_generator_func:
                doc_bytes = doc_generator_func(
                    student_data["firstName"],
                    student_data["lastName"],
                    student_data["organization"]["name"]
                )
                
                print("[*] Uploading document...")
                upload_res = self.upload_document(verification_id, doc_bytes)
                print(f"[*] Upload completed.")
                
                return self.check_status(verification_id)
            else:
                 return {"status": "DOC_REQUIRED_NO_GENERATOR"}
                 
        elif current_step == "reject": 
             return {"status": "REJECTED", "errors": result.get("errorIds")}
             
        return self.check_status(verification_id)
