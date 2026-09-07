import os
import json
import urllib.request
import urllib.parse
from pathlib import Path

# Load API key from .env
env_file = Path(r"c:\projects\Prompt2Render\.env")
key = None
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line.startswith("PIXABAY_API_KEY=") or line.startswith("PIXABAY_API_KEY ="):
            key = line.split("=", 1)[1].strip().strip("'\"")
            break

if not key:
    key = os.environ.get("PIXABAY_API_KEY")

if not key:
    raise RuntimeError("PIXABAY_API_KEY not found.")

out_dir = Path(r"c:\projects\Prompt2Render\projects\human-brain-problem\build\assets")
out_dir.mkdir(parents=True, exist_ok=True)

queries = [
    ("01_brain_neuroanatomy", "human brain anatomy organ"),
    ("02_eye_retina", "human eye retina pupil"),
    ("03_philosophy_descartes", "vintage antique book portrait statue"),
    ("04_fmri_scan", "mri brain scan radiology medical"),
    ("05_synapse_neuron", "neuron synapse microscopic cell"),
    ("06_quantum_cosmos", "universe cosmos stars space abstract network"),
]

for filename_prefix, query in queries:
    params = {
        "key": key,
        "q": query,
        "image_type": "photo",
        "per_page": 5,
        "safesearch": "true",
    }
    url = "https://pixabay.com/api/?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Prompt2Render/1.0"})
    with urllib.request.urlopen(req, timeout=12) as response:
        data = json.loads(response.read().decode("utf-8"))
        hits = data.get("hits", [])
        if hits:
            img_url = hits[0].get("webformatURL")
            dst = out_dir / f"{filename_prefix}.jpg"
            print(f"Downloading {filename_prefix} from {img_url} -> {dst}")
            img_req = urllib.request.Request(img_url, headers={"User-Agent": "Prompt2Render/1.0"})
            with urllib.request.urlopen(img_req, timeout=15) as img_resp:
                dst.write_bytes(img_resp.read())
        else:
            print(f"No hits for query '{query}'")

print("Asset download completed successfully!")
