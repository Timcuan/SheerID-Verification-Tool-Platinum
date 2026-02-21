import sheerid_api
import student_generator
import doc_generator
import config
import json
import os

def test():
    print("[*] Starting Local Test for SheerID Link...")
    # Ensure we use proxy from config
    proxy = config.PROXY_URL
    print(f"[*] Using Proxy: {proxy}")
    
    client = sheerid_api.SheerIDClient(proxy=proxy)
    
    # Generate profile
    profile = student_generator.generate_student_profile()
    name = profile["display_info"]["full_name"]
    university = profile["display_info"]["university"]
    print(f"[*] Generated Profile: {name} ({university})")
    
    url = "https://services.sheerid.com/verify/67c8c14f5f17a83b745e3f82/?verificationId=6999c2619edebc2d7d9a02a0"
    vid, is_program = client.extract_verification_id_from_url(url)
    
    def doc_gen(first, last, school):
        return doc_generator.generate_student_id(first, last, school)

    print(f"[*] Extract ID: {vid} (IsProgram: {is_program})")
    
    try:
        result = client.process_verification(vid, is_program, profile, doc_gen)
        print("\n" + "="*50)
        print("RESULT:")
        print(json.dumps(result, indent=2))
        print("="*50)
    except Exception as e:
        import traceback
        print(f"❌ TEST FAILED: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    test()
