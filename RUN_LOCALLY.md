# Running the Voice Slide Presenter locally

This guide takes you from a fresh checkout to talking with the presenter in your browser. The
[README](README.md) covers the architecture and design decisions.

## Prerequisites

| Tool | Version | Check |
| --- | --- | --- |
| [uv](https://docs.astral.sh/uv/) | any recent | `uv --version` |
| Node.js + npm | 20+ | `node --version` |
| LibreOffice (`soffice`) | any recent; needed for PPTX slide images | `soffice --version` |
| Azure OpenAI realtime deployment, or an OpenAI API key | - | - |

> **PPTX uploads work on macOS, Linux and Windows.** The app reads each slide's text and speaker
> notes with python-pptx, which is installed by `make install`. To show the slides as they really
> look (design, images, charts and layout), it also uses LibreOffice to render them to images, so
> install it once:
>
> ```bash
> brew install --cask libreoffice   # macOS
> # Linux: sudo apt-get install -y libreoffice-impress
> ```
>
> If LibreOffice is missing or broken, PPTX uploads still succeed and the presenter can still talk
> about every slide, but the slides are shown as text cards (title and bullet points) instead of
> images. `make check-deps` tells you when this will happen. PDF uploads and the built-in deck
> don't need LibreOffice. See [PPTX slides show only text](#pptx-slides-show-only-text) if you hit
> this.

All commands below are run from the project root (the folder that contains the `Makefile`).

## Quick start: commands in order

This is the exact sequence that was run on a Mac to get the app working. Run the commands one at
a time, and check each one's expected result before moving on. Sections 1 to 5 below explain each
step in more detail.

**1. Go to the project folder.** Quote the path if it contains spaces or `&`.

```bash
cd "/path/to/synthio_labs"
```

**2. Create your `.env` from the template.**

```bash
cp .env.example .env
```

Then open `.env` in an editor and set `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`,
`AZURE_OPENAI_REALTIME_DEPLOYMENT` and `TRANSCRIBE_MODEL`. See [step 1](#1-create-your-env) for
the values. `TRANSCRIBE_MODEL` is the one people forget; without a valid value, your own words
won't appear in the Transcript panel, and the screen won't automatically follow your spoken
questions.

**3. Install backend and frontend dependencies.**

```bash
make install
```

Expected result: `uv sync` resolves the Python packages, then `npm ci` ends with
`found 0 vulnerabilities`. On Node 23 you will also see `npm warn EBADENGINE` and an eslint
deprecation notice; both are harmless.

**4. Check your tools.**

```bash
make check-deps
```

Expected result:

```
ok   uv: uv 0.11.16 ...
ok   node: v23.9.0
ok   npm: 10.9.2
ok   soffice: LibreOffice <version> ...
ok   .env present
```

Any `MISSING` line must be fixed before continuing; see
[If `make check-deps` reports a problem](#if-make-check-deps-reports-a-problem). A `WARN soffice`
line means LibreOffice is missing or broken; the app still runs, but PPTX uploads will show
text-only slides until you install or reinstall it.

**5. Confirm Azure returns audio.**

```bash
make smoke
```

Expected result:

```
[smoke] provider=azure target=wss://<your-resource>/openai/v1/realtime?model=gpt-realtime
[smoke] connected in 1431 ms
[smoke] first audio after 748 ms
[smoke] OK: received 112800 bytes of PCM16 audio
```

If you get `HTTP 400`, the deployment name is wrong or isn't a realtime model. This happened
with `gpt-4o-mini`, and changing it to `gpt-realtime` fixed it. See
[Troubleshooting](#troubleshooting).

**6. Build and start the app.**

```bash
make serve
```

Expected result: the Vite build finishes (`✓ built in ...`), then
`Uvicorn running on http://127.0.0.1:8000`.

**7. Open the app.** Go to http://127.0.0.1:8000 in Chrome, pick the Synthio Labs deck, click
**Start** and allow the microphone. The server terminal should show
`WebSocket /ws?deck_id=synthio-labs [accepted]` and `connection open`.

**8. Stop the app** with `Ctrl+C` in the terminal running `make serve`.

## 1. Create your `.env`

```bash
cp .env.example .env
```

Open `.env` and fill in your credentials.

**Azure OpenAI (default):**

```bash
REALTIME_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_REALTIME_DEPLOYMENT=<your realtime deployment name, e.g. gpt-realtime>
TRANSCRIBE_MODEL=<your transcription deployment name, e.g. gpt-4o-transcribe>
```

Endpoints on `*.cognitiveservices.azure.com` work too. The deployment must be a **realtime**
model (such as `gpt-realtime`). A regular chat deployment like `gpt-4o-mini` is rejected with
HTTP 400.

**OpenAI instead of Azure:**

```bash
REALTIME_PROVIDER=openai
OPENAI_API_KEY=<your-key>
TRANSCRIBE_MODEL=gpt-4o-transcribe
```

### Transcription: `TRANSCRIBE_MODEL`

The realtime model listens to your voice directly, so the presenter understands you and answers
whether or not transcription works. `TRANSCRIBE_MODEL` is a **second** model that turns your speech
into text. The app needs that text for two things:

- **The Transcript panel.** The presenter's side of the transcript comes from the realtime model
  and always shows up. Your side only appears if `TRANSCRIBE_MODEL` works; otherwise each of your
  turns shows as `(voice message - transcription unavailable)`.
- **Auto-navigation.** When your question clearly matches one slide, the server moves the screen
  there even if the agent forgets to. It does this from the text of your question, so for spoken
  questions it needs working transcription. Without it, slides only change when the agent calls
  a navigation tool. See
  [MULTI_AGENT_WORKFLOW.md](MULTI_AGENT_WORKFLOW.md#auto-navigate-the-servers-safety-net).

How to set it:

| Provider | What `TRANSCRIBE_MODEL` must be | Default |
| --- | --- | --- |
| Azure | the **deployment name** of a transcription model in the **same Azure resource** as your realtime deployment | `gpt-4o-transcribe` |
| OpenAI | a transcription model name | `gpt-4o-transcribe` |

The default, `gpt-4o-transcribe`, is set in `.env.example` and is also the fallback if the line is
missing from `.env`.

On Azure, deploy a transcription model (for example `gpt-4o-transcribe` or
`gpt-4o-mini-transcribe`) in Azure AI Foundry, in the same resource as `gpt-realtime`. Then put
that deployment's name, not the model name, in `TRANSCRIBE_MODEL`. If your deployment is named
exactly `gpt-4o-transcribe`, the default already works and you don't need to change anything.

If the value is wrong, voice still works, but the app shows this error after your first spoken
turn:

```
Your speech could not be transcribed, so it won't appear in the transcript. No deployment named
'gpt-4o-transcribe' exists; set TRANSCRIBE_MODEL in .env to your transcription deployment name.
```

`make smoke` does **not** test transcription, because it only checks that the realtime deployment
returns audio. To check transcription, start the app, say something, and confirm your words
appear in the Transcript tab.

### Other optional settings

The defaults are fine:

| Variable | Default | Purpose |
| --- | --- | --- |
| `REALTIME_VOICE` | `ash` | the presenter's voice |
| `REALTIME_SPEED` | `1.15` | speaking speed, `0.25`-`1.5`; lower it (e.g. `1.0`) for a slower, more deliberate pace |
| `AGENT_MODE` | `multi` | `multi` = Presenter + Deck Expert with handoffs; `single` = one agent, slightly faster |
| `GROUNDING_GUARDRAIL` | `true` | `false` turns off the guardrail that cuts the agent off when it states a figure not in the deck |
| `VAD_EAGERNESS` | `auto` | set to `low` if the presenter keeps interrupting itself on speakers |

`.env` is gitignored, so your keys never get committed.

## 2. Install dependencies and check your setup

```bash
make install       # uv sync (backend) + npm ci (frontend)
make check-deps    # checks uv, node, npm, soffice and .env
```

You may see an `npm warn EBADENGINE` line on Node 23, or a deprecation notice for eslint 9. Both
are harmless.

If `check-deps` prints `WARN soffice is on PATH but fails to run` (or `soffice ... not found`),
PPTX uploads will show text-only slides until LibreOffice is installed. Everything else still
works: the built-in deck, PDF uploads, voice, navigation and interruption. See the fixes below.

### If `make check-deps` reports a problem

Each line of `make check-deps` output maps to one fix below. The commands are for macOS with
[Homebrew](https://brew.sh); Linux equivalents follow each one. After installing anything, open a
**new terminal window** so your `PATH` picks it up, then run `make check-deps` again.

If you don't have Homebrew yet, install it first:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**`MISSING uv`**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # macOS and Linux
# or on macOS: brew install uv
uv --version
```

The installer puts `uv` in `~/.local/bin`. If `uv` still isn't found in a new terminal, add that
folder to your `PATH`.

**`MISSING node (>= 20)` or `MISSING npm`**

npm comes with Node.js, so one install fixes both.

```bash
brew install node                 # macOS
# Linux: install Node 22 LTS from https://nodejs.org or with nvm
node --version                    # should be v20 or newer
npm --version
```

Node 20.19+, 22.13+ or 24+ avoids the `EBADENGINE` warning. Node 23 also works and only prints
that warning.

**`WARN soffice (LibreOffice) not found`** (needed for PPTX slide images)

```bash
brew install --cask libreoffice   # macOS
# Linux: sudo apt-get install -y libreoffice-impress
soffice --version
```

**`WARN soffice is on PATH but fails to run`** (needed for PPTX slide images)

The `soffice` command exists but can't start LibreOffice. On macOS this usually means
`/Applications/LibreOffice.app` was deleted or moved while Homebrew's `soffice` link was left
behind. Reinstall it:

```bash
brew reinstall --cask libreoffice
soffice --version                 # should print a version, not an error
```

If you skip this, the app still works: PPTX uploads use text-only slides, and PDF uploads are
unaffected.

**`WARN .env missing`**

```bash
cp .env.example .env
```

Then fill in your keys as described in [step 1](#1-create-your-env).

Once every line says `ok`, run `make install` again if it failed earlier. (`soffice` can stay a
`WARN` if you only use PDFs and the built-in deck.)

## 3. Confirm the model returns audio

```bash
make smoke
```

A working setup prints something like:

```
[smoke] connected in 1431 ms
[smoke] first audio after 748 ms
[smoke] OK: received 112800 bytes of PCM16 audio
```

If this fails, the browser app will fail too, so fix it before going further. See
[Troubleshooting](#troubleshooting).

Optionally, check the agent's behaviour too (about a minute, a few cents of API usage):

```bash
make eval
```

This runs 18 scripted conversations (navigation, answers from the deck, off-topic and dosing
questions, prompt-injection attempts) and prints PASS/FAIL for each, plus a summary. A pass rate
of 90% or more is a healthy setup; the model is not fully deterministic, so an occasional single
failure is normal. See [Evals](README.md#evals) for options.

## 4. Start the app

Pick one:

```bash
make serve    # builds the frontend, then serves everything at http://127.0.0.1:8000
```

```bash
make dev      # hot reload: backend on :8000, Vite on :5173; open http://localhost:5173
```

Use `make serve` for demos and `make dev` while changing code. Press `Ctrl+C` in the terminal to
stop either one.

## 5. Use it

Chrome works best.

1. Pick the built-in **Synthio Labs** deck, or drag a `.pptx` or `.pdf` onto the upload area
   (25 MB and 40 slides max).
2. Click **Start** and allow microphone access. The presenter greets you and presents slide 1.
3. Ask a question out loud, for example:
   - "What products do you have?" (jumps to slide 4)
   - "How do you keep answers compliant?" (jumps to slide 5)
   - "Next", or "go back to integrations"
4. Talk over the presenter at any time. It stops speaking and answers what you just said.
5. Click a thumbnail or use the arrow keys to change slides yourself; the presenter picks up from
   the new slide.

Other controls:
- **Space** toggles mute.
- **Interrupt** stops the presenter mid-sentence.
- You can type a question in the text box instead of speaking.
- **Stop** ends the session; **Restart** reconnects.
- The **Transcript** tab shows both sides of the conversation.
- The **Agent Activity** tab streams which agent is responding, tool calls with their results,
  handoffs, guardrail passes and trips, blocked inputs, and a live eval of every spoken reply.

**Wear headphones.** On laptop speakers the presenter can hear itself and interrupt its own
speech. If you have to use speakers, set `VAD_EAGERNESS=low` in `.env` and restart.

## Troubleshooting

### `make smoke` fails with HTTP 400

The deployment name in `AZURE_OPENAI_REALTIME_DEPLOYMENT` is wrong, or it points to a model that is
not a realtime model. Check the exact deployment name in Azure AI Foundry and make sure its model
is `gpt-realtime` (or another realtime model).

### `make smoke` fails with HTTP 401 or 403

The API key is wrong or belongs to a different resource than `AZURE_OPENAI_ENDPOINT`.

### `make smoke` says the provider is not configured

`.env` is missing, or some variables for the selected `REALTIME_PROVIDER` are empty. The message
lists which ones are missing.

### The page loads but nothing happens after Start

- Check that the browser has microphone permission for the site.
- Look at the terminal running the server for errors after `WebSocket /ws ... [accepted]`.
- Open `http://127.0.0.1:8000/api/health`; it shows the provider, agent mode and whether
  credentials are configured.

### "Your speech could not be transcribed" / your words are missing from the transcript

`TRANSCRIBE_MODEL` doesn't match a transcription deployment. On Azure it must be the
**deployment name** of a transcription model (such as `gpt-4o-transcribe`) in the same
resource as your realtime deployment. Fix `.env`, then restart the server (`Ctrl+C`, then
`make serve`). The presenter keeps working in the meantime. What's missing is your side of the
transcript, plus the server's automatic slide-following for spoken questions. See [Transcription: `TRANSCRIBE_MODEL`](#transcription-transcribe_model).

### The presenter keeps cutting itself off

This is echo from your speakers. Use headphones, or set `VAD_EAGERNESS=low` in `.env`.

### Responses feel slow

Set `AGENT_MODE=single` to skip handoffs between the two agents. The latency readout in the
bottom bar shows the time from the end of your speech to the first audio.

### PPTX slides show only text

You'll see the message "LibreOffice failed to render the deck; showing text-only slides" (or
"LibreOffice (soffice) is not installed"). python-pptx has read the text and notes, but
LibreOffice, which turns the slides into images, is missing or can't start. `make check-deps`
shows which. The server log has the details, for example
`soffice failed: ... returned non-zero exit status 127`, where 127 means the LibreOffice app that
`soffice` points to doesn't exist. The upload itself succeeds, and the reason is also returned in
an `X-Deck-Warning` response header. Pick one fix:

**Install or reinstall LibreOffice:**

```bash
brew install --cask libreoffice     # or: brew reinstall --cask libreoffice
# Linux: sudo apt-get install -y libreoffice-impress
soffice --version     # should print a version, not an error
make check-deps       # should now print "ok   soffice: ..."
```

Restart the server afterwards, then upload the PPTX again. Decks you uploaded earlier stay
text-only.

**Upload a PDF instead.** Export the deck from PowerPoint or Keynote (File > Export > PDF) and
upload that. PDFs render as real slide images without LibreOffice.

**Run in Docker,** which bundles LibreOffice:

```bash
make docker-build
make docker-run       # http://127.0.0.1:8000, reads your .env
```

### Port 8000 is already in use

Run on another port, for example `make serve PORT=8001`. If you use `make dev`, the Vite proxy
expects the backend on 8000, so stop whatever else is using that port instead.

## Useful commands

| Command | What it does |
| --- | --- |
| `make test` | runs the 46 backend tests (no keys needed) |
| `make lint` | ruff check, ruff format check, tsc, and eslint |
| `make fmt` | applies ruff fixes and formats the backend |
| `make check` | lint, format check, pytest, and the frontend production build (same as CI) |
| `make install-ci` | install from the lockfiles without updating them (what CI runs first) |
| `make sample-pptx` | writes `backend/samples/sample_deck.pptx` for testing uploads |
| `make clean` | removes build output, caches and uploaded decks |
| `make help` | lists every target |
