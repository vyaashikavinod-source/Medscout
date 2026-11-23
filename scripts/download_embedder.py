"""Download immutable, public model assets. No remote model code executes."""
from pathlib import Path
import urllib.request, hashlib, json, os
REVISION="751bff37182d3f1213fa05d7196b954e230abad9"
base=f"https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/{REVISION}/"
target=Path(os.getenv("MEDSCOUT_EMBED_DIR","/app/embedding-model"));target.mkdir(parents=True,exist_ok=True)
manifest={"model":"Xenova/all-MiniLM-L6-v2","revision":REVISION,"quantization":"int8 ONNX","files":{}}
for source,name in [("onnx/model_quantized.onnx","model.onnx"),("tokenizer.json","tokenizer.json")]:
    path=target/name
    if not path.exists():
        with urllib.request.urlopen(base+source,timeout=120) as response,path.open("wb") as output:
            while chunk:=response.read(1024*1024):output.write(chunk)
    manifest["files"][name]={"bytes":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
(target/"manifest.json").write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest))
