# Fence in 60 seconds

## Before the clock

Activate the environment from the app directory and follow the [README setup](../README.md). Use a dedicated synthetic bank and queue for any rehearsal that saves outcomes or votes. Keep the existing demo bank and queue for read-only use during preparation. For a fresh rehearsal, choose an unused bank ID and queue path, then run:

```bash
export HINDSIGHT_BANK_ID=fence-rehearsal-01
export OUTCOME_QUEUE_PATH="$PWD/.data/rehearsal-01.sqlite3"
python -m seed.seed --dry-run
python -m seed.seed
python -m streamlit run app.py --server.address=127.0.0.1 --server.port=8501
```

The dry run should report 14 unique decisions. Seeding writes those decisions to the selected bank. Allow seeding to finish and open <http://localhost:8501> before starting. If reusing an already seeded rehearsal bank, skip the live seed. To show a populated Patterns section, prepare confirmed synthetic outcomes covering at least two distinct proposal/source groups and run a rehearsal reflection. A fresh queue can legitimately return no supported pattern. Keep the screenshots below open in order.

## 60-second presentation: captured live results

Use this mode for a strict one-minute slot. Open the four linked captures before starting. They are real provider-backed results from isolated synthetic QA data, **not newly generated results**. Say that explicitly. Do not wait for new API requests during this presentation.

| Time budget | Show | Narration |
| --- | --- | --- |
| 0–15s | [Lotus comparison](qa/stage7b-desktop.jpg) | These are captured results from a real Fence run with synthetic data. Teams repeat mistakes when decision context disappears. Lotus lost thirty-one percent of merchants in six weeks after removing its free tier. |
| 15–28s | Comparison, then [Lotus citation](qa/stage7b-mobile-evidence.jpg) | Fence checks a new pricing proposal with and without memory. The grounded answer cites Lotus and recommends a pilot, checking support capacity, competitor timing, and migration. |
| 28–43s | [Persisted learning](qa/stage7b-desktop-learning.jpg) | Outcomes persist. Confirmed relevance votes influence later evidence ranking; this chart measures votes, not accuracy. Duplicate submissions count once. |
| 43–58s | [Reflection sources](qa/stage7b-desktop-reflection.jpg) | Reflection links recurring themes to verified sources. It runs on demand or after three qualifying outcomes. Fence brings past decisions into the next review. |
| 58–60s | Hold final frame | Stop; take questions outside the timed slot. |

**Timing evidence:** the exact 102-word narration was rendered locally with the installed macOS Samantha voice at 145 words/minute. The resulting [reference narration](qa/stage7d-narration.aiff) is **46.273 seconds**, leaving 13.727 seconds for transitions/pauses. This verifies the narration duration, not a human-delivered presentation or a fresh live workflow. Rehearse the four prepared transitions while speaking; do not claim the full live acceptance criterion passed based on this recording.

## Live workflow outside the strict presentation slot

The complete Stage 7D Chrome run took **67.626 seconds without narration**, including automation overhead; review generation itself took **6.25 seconds**. Reflection was still running at 58.237 seconds. The original full live workflow has therefore **not passed** the 60-second criterion. Provider latency cannot be made reliable by shortening narration alone.

For a live demonstration, preload the sample, prefill a synthetic outcome note, and keep the four captures open. Speak while requests run, omit archive browsing, and switch to the explicitly labeled prior capture if a request overruns its slot. Do not describe the fallback as a newly completed save or reflection. A duplicate vote does not update the chart; use an isolated unused proposal/evidence association when demonstrating a new vote. Do not rewrite existing events or reseed the demonstration bank. A strict live-only acceptance still needs a measured successful run including narration.

The sample is: “Remove the free tier for small merchants and move them to a Rs 299/month plan next quarter.” Check it, compare the answers, follow Lotus's evidence citation, save a Pending outcome with supporting notes, mark the lesson Relevant, inspect the confirmed chart, and request **What does our history say?** Pending does not advance automatic reflection. Empty histories may correctly produce no supported pattern.

## Backup proposals

These match distinct seed records. The expected precedents are rehearsal targets because live retrieval and generated wording can vary.

| Copy into the proposal editor | Look for |
| --- | --- |
| Offer instant merchant settlement for eligible payment flows next month before completing a fraud-ops review. Use account age for eligibility and skip transaction-velocity controls for the initial launch. | **Instant Settlement** was rolled back after ₹38 lakh in month-one chargebacks. Check fraud review and release controls. |
| Move merchant login OTP messages to a cheaper SMS provider next month to cut per-message costs by 22%. Roll out to tier-2 merchants before benchmarking OTP delivery. | **SMS provider switch** reached 91% tier-2 OTP delivery and was reversed within three weeks. Check delivery and rollback readiness. |
| Pilot QR soundboxes with 400 merchants in Mysuru. Expand to five more cities after payment-alert delivery, weekly usage, and support ticket gates hold for four weeks. | **QR soundbox rollout**, a successful single-city pilot. Check the actual gates and local replacement readiness before expansion. |
