import sys
import subprocess
import importlib.util
import re

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

def check_package(package_name):
    spec = importlib.util.find_spec(package_name)
    return spec is not None

def get_installed_version(package_name):
    try:
        result = subprocess.run([sys.executable, "-m", "pip", "show", package_name], capture_output=True, text=True)
        for line in result.stdout.split('\n'):
            if line.startswith("Version: "):
                return line.split(": ")[1]
        return "Not found"
    except:
        return "Error"

def normalize_requirement_name(requirement):
    return re.split(r'[<>=!~]', requirement, 1)[0].strip()

def check_cuda():
    try:
        import torch
        print(f"Torcy Version: {torch.__version__}")
        if torch.cuda.is_available():
            print(f"✅ CUDA is available. Version: {torch.version.cuda}")
            print(f"   Device: {torch.cuda.get_device_name(0)}")
            return True
        else:
            print("⚠️ CUDA is NOT available. Using CPU.")
            return False
    except ImportError:
        print("⚠️ PyTorch is not installed.")
        return False

print("---- Python Environment Check ----")
print(f"Python Executable: {sys.executable}")
print(f"Python Version: {sys.version}")

print("\n---- Dependency Check ----")
req_file = "requirements.txt"
try:
    with open(req_file, 'r') as f:
        requirements = [
            normalize_requirement_name(line.strip())
            for line in f
            if line.strip() and not line.startswith('#')
        ]
    
    package_mappings = {
        "python-dotenv": "dotenv",
        "scikit-learn": "sklearn",
        "kiwipiepy": "kiwipiepy" # explicit just in case
    }

    all_installed = True
    for req in requirements:
        import_name = package_mappings.get(req, req)
        if check_package(import_name):
            print(f"✅ {req}: Installed (found '{import_name}')")
        else:
             # Fallback to pip show if import fails
            version = get_installed_version(req)
            if version != "Not found" and version != "Error":
                 print(f"✅ {req}: Installed (via pip show) - {version}")
            else:
                print(f"❌ {req}: MISSING")
                all_installed = False
except FileNotFoundError:
    print(f"⚠️ {req_file} not found.")

print("\n---- GPU/CUDA Check ----")
check_cuda()
