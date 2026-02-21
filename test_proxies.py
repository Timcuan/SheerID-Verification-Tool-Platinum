import requests
import concurrent.futures

proxies_list = [
    "23.95.150.145:6114",
    "198.23.239.134:6540",
    "216.10.27.159:6837",
    "107.172.163.27:6543",
    "45.38.107.97:6014",
    "198.105.121.200:6462",
    "64.137.96.74:6641",
    "142.111.67.146:5611",
    "23.26.53.37:6003",
    "31.59.20.176:6754"
]

auth = "pxssjjhe:awdy9sipxzln"

def check_proxy(proxy_endpoint):
    proxy_url = f"http://{auth}@{proxy_endpoint}"
    proxies = {"http": proxy_url, "https": proxy_url}
    
    try:
        resp = requests.get("http://ip-api.com/json/?fields=status,message,country,isp,org,as,mobile,proxy,hosting,query", proxies=proxies, timeout=5)
        data = resp.json()
        
        if data['status'] == 'success':
            return {
                "ip": data['query'],
                "country": data['country'],
                "isp": data['isp'],
                "hosting": data['hosting'],
                "endpoint": proxy_endpoint,
                "score": calculate_score(data)
            }
    except:
        pass
    return None

def calculate_score(data):
    score = 0
    if data['country'] == 'United States': score += 20
    if not data['hosting']: score += 50
    if not data['proxy']: score += 10
    
    bad_isps = ['ColoCrossing', 'RackNerd', 'DigitalOcean', 'Choopa', 'Datacenter', 'Host', 'Cloud']
    if any(b.lower() in data['isp'].lower() for b in bad_isps):
        score -= 30
        
    good_isps = ['Comcast', 'AT&T', 'Verizon', 'Charter', 'Spectrum']
    if any(g.lower() in data['isp'].lower() for g in good_isps):
        score += 50
        
    return score

print("Checking 6 proxies from your list...")
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    results = list(executor.map(check_proxy, proxies_list))

best_proxy = None
max_score = -100

for res in results:
    if res:
        status = "✅ RESI" if not res['hosting'] else "❌ DC"
        print(f"[{status}] {res['ip']} | ISP: {res['isp']} | Score: {res['score']}")
        if res['score'] > max_score:
            max_score = res['score']
            best_proxy = res

if best_proxy:
    print(f"\n🏆 Best Proxy: {best_proxy['endpoint']} ({best_proxy['isp']})")
    
    # Update config.py automatically
    import config
    
    # Read original file
    with open('config.py', 'r') as f:
        lines = f.readlines()
        
    # Rewrite with new proxy
    with open('config.py', 'w') as f:
        for line in lines:
            if "USE_PROXY =" in line:
                f.write("USE_PROXY = True\n")
            elif "PROXY_URL =" in line:
                f.write(f'PROXY_URL = "http://{auth}@{best_proxy["endpoint"]}"\n')
            else:
                f.write(line)
    
    print("✅ updated config.py with this proxy!")
else:
    print("\n❌ All proxies failed or are poor quality.")
