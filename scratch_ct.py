import requests
import json

r = requests.get('https://clinicaltrials.gov/api/v2/studies?query.cond=Surgery&pageSize=1')
with open('scratch_ct.json', 'w', encoding='utf-8') as f:
    json.dump(r.json(), f, indent=2)
