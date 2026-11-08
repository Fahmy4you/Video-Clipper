# 9Router, source reuse, and the heavy-work queue

Home creates a review project and an initial proposal search. The transcription page is
`/transcriptions`; the video page is `/projects`. Both use the same project ID.

## Setup

Set these keys in the root `.env`:

```dotenv
9router_base_url=http://WINDOWS_HOST:20128/v1
9router_key=YOUR_9ROUTER_KEY
```

Use a key created by 9Router. When the backend runs in WSL and the router runs in Windows,
use the Windows host address reachable from WSL, rather than assuming Linux localhost
reaches Windows. Inspect the WSL default route with `ip route show default` and verify
the router permits access on that address. If both services share a network namespace,
`http://127.0.0.1:20128/v1` can be used.

The backend reads these two settings before each request. Empty values stop new AI work
with an actionable message. In-flight requests retain their original configuration.
Never commit the real key. The example environment file intentionally has empty values.

The app no longer reads `apikey.json` or Google API keys. Existing private key files remain
ignored by Git. Account connections, combo membership and fallback are managed by 9Router.

## Processing

1. Download audio and transcribe using local Whisper with chunk checkpoints.
2. Send compact timestamped text to the selected combo to propose 30–90-second highlights.
3. Review the proposals and revise their range or processing settings.
4. Approve each desired proposal. The full video, up to 1080p, is prepared once per source.
5. Build the edit plan and optional Mix, then open Studio. MP4 creation remains under Export.

Additional proposal searches reuse the transcript. Each search has its own immutable
prompt/count/combo/exclusion snapshot and completion marker. Deleting a proposal does not
cause retries to recreate it. Transcription sources are identified by canonical YouTube ID.
Project-specific assets and edit plans remain independent even when projects reuse a source.

## Downloads and recovery

Format-specific partial files are retained. Network reads have a 60-second timeout and
bounded retries. Missing fragments cannot be silently skipped. The final file is published
only after media inspection. Network waits release the global heavy-work slot.

Temporary waits are checked after 1, 5, then 15 minutes, respecting longer Retry-After
values. After the automatic limit, the user can explicitly check again. A 429 is described
as a request limit, not assumed to mean the daily quota is exhausted.

Interrupted Google jobs require explicit selection of a combo and
**Lanjutkan dengan 9Router**. Existing source files, transcripts and completed work remain.
The application does not try individual combo members or cycle through account keys.

Deleting a project does not delete a shared source used by another project. Last-reference
cleanup removes the shared source cache. Original exports in a user-selected external
Local export folder retain their existing deletion policy.

## Local verification

`npm run format:check`, `npm run build`, and `npm test` validate formatting, frontend and
backend. Provider tests use fake HTTP transports and never send paid test prompts.
The metadata connection check performs only GET /v1/models.
