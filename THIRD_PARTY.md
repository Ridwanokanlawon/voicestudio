# Third-party components

Voice Studio's own code is in `app\`. It uses these components.

| Component | Where it is | Licence | Source |
|---|---|---|---|
| YarnGPT code (`audiotokenizer.py`, speaker presets) | `vendor\yarngpt\` | MIT (stated in its README) | https://github.com/saheedniyi02/yarngpt |
| YarnGPT2 model weights | `models\hf\YarnGPT2\` (downloaded by Setup, not in the repository) | Apache-2.0 | https://huggingface.co/saheedniyi/YarnGPT2 |
| WavTokenizer checkpoint and config | `models\` (downloaded by Setup, not in the repository) | MIT | https://github.com/jishengpeng/WavTokenizer |
| PyTorch, Transformers, OuteTTS, FastAPI and other Python packages | `runtime\` (installed by Setup with pip, not in the repository) | each package's own licence | https://pypi.org |
| Azure AI Speech SDK | `runtime\` (installed by Setup with pip) | Microsoft licence; needs your own Azure key | https://pypi.org/project/azure-cognitiveservices-speech/ |

Model weights and Python packages are never committed to the repository. Each
PC downloads them from the original publisher during Setup.

YarnGPT citation: Saheed Azeez (2025), YarnGPT: Nigerian-Accented English Text-to-Speech Model, Hugging Face.
