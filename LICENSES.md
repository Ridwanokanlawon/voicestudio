# Licences

Checked on 16 and 26 November 2026 from PyPI, GitHub and Hugging Face. Re-check before
upgrading any version below.

## What is in the Voice Studio folder and repository
Only Voice Studio's own code (`app\`), icons, and setup scripts. No third-party
code, packages or model weights are stored in the repository or in the small
share zip. Setup downloads each of them from its original publisher onto each PC.

## Voice engines and model weights (downloaded by Setup)

| Item | Used for | Licence | Commercial use | Size | Source |
|---|---|---|---|---|---|
| chatterbox-tts 0.1.7 | Chatterbox code | MIT | Yes | small | pypi.org/project/chatterbox-tts |
| ResembleAI/chatterbox (ve, t3_cfg, s3gen, tokenizer, conds) | Chatterbox English weights | MIT | Yes | 3.2 GB | huggingface.co/ResembleAI/chatterbox |
| resemble-perth 1.0.1 | Chatterbox audio watermark (kept on) | MIT | Yes | small | pypi.org/project/resemble-perth |
| s3tokenizer 0.3.0 | Chatterbox dependency | Apache-2.0 | Yes | small | pypi.org/project/s3tokenizer |
| OpenVoice (commit 74a1d14) | Tone colour converter code | MIT | Yes | small | github.com/myshell-ai/OpenVoice |
| myshell-ai/OpenVoiceV2 (converter, English base speakers) | Tone colour converter weights | MIT | Yes | 131 MB | huggingface.co/myshell-ai/OpenVoiceV2 |
| MeloTTS (commit 2091453) | Base voice code | MIT | Yes | small | github.com/myshell-ai/MeloTTS |
| myshell-ai/MeloTTS-English | EN-US, EN-BR, EN-AU, EN-Default, EN-India voices | MIT | Yes | 208 MB | huggingface.co/myshell-ai/MeloTTS-English |
| bert-base-uncased | Text model MeloTTS needs for English | Apache-2.0 | Yes | 440 MB | huggingface.co/google-bert/bert-base-uncased |
| wavmark 0.0.3 and M4869/WavMark | OpenVoice audio watermark (kept on) | MIT | Yes | small | pypi.org/project/wavmark |
| g2p_en 2.1.0 | English pronunciation | Apache-2.0 | Yes | small | pypi.org/project/g2p-en |
| NLTK data: cmudict, averaged_perceptron_tagger | Pronunciation data | cmudict: unrestricted for research or commercial use, credit Carnegie Mellon University; tagger: MIT | Yes | 13 MB | nltk.org/nltk_data |
| kokoro 0.9.4, misaki 0.9.4 | Kokoro code and its text front end | Apache-2.0 | Yes | small | pypi.org/project/kokoro |
| hexgrad/Kokoro-82M | Kokoro weights and preset voices | Apache-2.0 | Yes | 330 MB | huggingface.co/hexgrad/Kokoro-82M |
| spaCy 3.8 and en_core_web_sm 3.8.0 | English text analysis for Kokoro | MIT | Yes | 13 MB | github.com/explosion/spacy-models |
| PyTorch 2.6.0, torchaudio 2.6.0 | Runs the models | BSD-3-Clause | Yes | 2.5 GB (GPU build) | pytorch.org |
| Azure AI Speech SDK | Azure voices (cloud, your own key) | Microsoft Software License Terms | Yes, under your Azure subscription terms | small | pypi.org/project/azure-cognitiveservices-speech |

## Other Python packages
The exact versions are listed in `requirements.txt`, `requirements-chatterbox.txt`
and `requirements-openvoice.txt`. A scan of the engine environments (76, 84 and 103
packages) found only permissive licences (MIT, BSD, Apache-2.0, ISC, PSF), with
these exceptions, none of which restrict use or sharing of this app:

| Package | Licence | Note |
|---|---|---|
| soxr | LGPL-2.1-or-later | Resampling library, used unmodified as a separate installed package |
| certifi, tqdm | MPL-2.0 (tqdm: MPL-2.0 and MIT) | Used unmodified |
| eng_to_ipa | Package metadata is blank. Its repository states MIT; not independently confirmed | Small text helper |

GPL components in the light environment (`envs\lite`): Kokoro's text front end uses
phonemizer-fork (GPL-3.0-or-later) and espeak-ng through espeakng-loader (espeak-ng is
GPL-3.0-or-later) to pronounce words that are not in its dictionary, and num2words
(LGPL-2.1). Setup installs them from PyPI as separate packages; Voice Studio does not
modify or bundle them, and using them places no restriction on the audio you make. They
would matter only if the environments were ever bundled into one installer: the GPL
then requires offering their source.

Removed in 0.5.0: Pocket TTS (Kyutai), with its code, weights and preset voices. Nothing
from it is installed by setup any more. Audio you already made with it keeps its credit
line: "Voice: Pocket TTS by Kyutai (CC BY 4.0)".

Left out on purpose: the upstream projects list a few GPL or LGPL helper packages
that are only needed for languages or code paths Voice Studio does not use
(pykakasi and spacy-pkuseg for Chatterbox; Unidecode, Distance and num2words for
OpenVoice and MeloTTS). Setup does not install them.

## If the app is ever shipped as one packaged installer
The table above covers the current design, where each PC downloads components
itself. An installer that bundles the Python environments or model weights
must include each component's licence text, and the LGPL library (soxr) must
stay replaceable.

## Voice cloning
Voice profiles are for your own voice, or a voice whose owner has given written
permission. The engines' built-in watermarks are left switched on, and exported
files carry "AI-generated voice" in their metadata.

## Retired
YarnGPT (MIT code, Apache-2.0 weights, WavTokenizer MIT) was removed in 0.2.0.
