# Ollama Setup Guide for Local-Sage

## Prerequisites

Ollama is required to run the full agent loop with code generation.

## Installation

### Windows

1. **Download Ollama** from https://ollama.ai
2. **Run the installer** and follow the prompts
3. **Verify installation**:
   ```powershell
   ollama --version
   ```

### macOS

```bash
brew install ollama
```

### Linux

```bash
curl https://ollama.ai/install.sh | sh
```

---

## Starting Ollama

### Windows (PowerShell)
```powershell
ollama serve
```

### macOS/Linux
```bash
ollama serve
```

**Expected output:**
```
2024/06/14 14:00:00 "GET /api/tags HTTP/1.1" 200 45
```

This starts Ollama server on `http://localhost:11434`

---

## Pulling the Model

**In a NEW terminal** (keep `ollama serve` running):

```powershell
ollama pull qwen2.5-coder:7b
```

**Expected output:**
```
pulling digest sha256:...
pulling 637b...
pulling 0d4...
pulling d3e...
verifying sha256 digest
writing manifest
success
```

This downloads ~4.7GB. First pull takes 5-10 minutes.

---

## Verify Setup

### Check Model is Available

```powershell
ollama list
```

**Expected output:**
```
NAME                 ID              SIZE      MODIFIED
qwen2.5-coder:7b     1234567890ab    4.7 GB    2 minutes ago
```

### Check Ollama Health

```powershell
$response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags"
$response.StatusCode
```

Should return `200`

---

## Running Local-Sage with Ollama

### Step 1: Start Ollama (Terminal 1)
```powershell
ollama serve
```

### Step 2: Verify Model (Terminal 2)
```powershell
ollama list
```

### Step 3: Run Demo (Terminal 3)
```powershell
cd "c:\Users\USER\sidaarth\SLM research"
python demo_clean.py
```

### Step 4: Run Full Agent (Terminal 3)
```powershell
python -c "
from pathlib import Path
from local_sage.orchestration.graph import build_graph
from local_sage.orchestration.state import AgentState
from local_sage.memory.session import SessionManager
from local_sage.config import load_config

config = load_config()
repo_root = Path.cwd()
sm = SessionManager(repo_root / config.sage_dir / 'memory.db')
session = sm.load_latest_session(repo_root) or sm.create_session(repo_root)

graph = build_graph()
result = graph.invoke(AgentState(
    task='Fix the divide-by-zero bug in app.py',
    max_retries=3,
    session_id=session.session_id,
))
print('Result:', result)
"
```

---

## Troubleshooting

### Error: "Failed to connect to localhost port 11434"

**Solution**: Ollama server is not running
```powershell
ollama serve
```

### Error: "model not found"

**Solution**: Pull the model first
```powershell
ollama pull qwen2.5-coder:7b
```

### Error: "dial tcp [::1]:11434: connectex: No connection could be made"

**Solution**: Windows Firewall blocking connection. Allow Ollama through firewall:
1. Windows Defender Firewall → Allow an app through firewall
2. Find Ollama and check both Private and Public
3. Restart ollama serve

### Model Takes Too Long to Respond

**Normal behavior** for first run (~2-5 minutes to generate code)
- Model is running locally on consumer hardware
- Qwen2.5-Coder 7B is not as fast as cloud APIs
- Patience is key!

### Out of Memory (OOM)

**Solution**: Reduce model size (optional)
```powershell
ollama pull qwen2:7b            # Smaller general model
ollama pull neural-chat:7b       # Another option
```

---

## Model Details

- **Name**: qwen2.5-coder:7b
- **Size**: 4.7 GB
- **Architecture**: 7 billion parameters
- **Speed**: ~1-2 tokens/second on CPU, faster on GPU
- **License**: Apache 2.0
- **Training**: Specialized for code generation

---

## Testing Ollama

### Quick Test Request

```powershell
$body = @{
    "model" = "qwen2.5-coder:7b"
    "prompt" = "def hello():"
    "stream" = $false
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://localhost:11434/api/generate" `
  -Method Post `
  -Body $body `
  -ContentType "application/json"
```

Should return JSON with `response` field containing generated code.

---

## Performance Tips

1. **Use GPU if available**: Ollama auto-detects CUDA/Metal
2. **Reduce model size** if running on low-RAM machines
3. **Increase timeout** in `sage.toml` if responses are slow
4. **Keep ollama serve running** - don't restart between tasks

---

## Next Steps

1. ✓ Install Ollama
2. ✓ Start `ollama serve`
3. ✓ Pull `qwen2.5-coder:7b`
4. ✓ Run `python demo_clean.py` to verify all components
5. ✓ Run full agent loop with a coding task

All 12 components are ready!
