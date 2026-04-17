import requests, json

r = requests.post('http://localhost:8001/ai/analyze-image', 
    files={'file': open('static/faces/face_20260416153041_0.jpg','rb')})

d = r.json()
print('STATUS:', r.status_code)
print('PEOPLE:', d['summary']['people_found'])
print('HAZARDS:', d['summary']['hazards_found'])
print()
for i, x in enumerate(d['detections']):
    print(f"Detection #{i}:")
    print(f"  face_name = {x.get('face_name')}")
    print(f"  ocr_code  = {x.get('ocr_code')}")
    print(f"  confidence = {x.get('confidence')}")
    print(f"  label     = {x.get('label')}")
    print()
