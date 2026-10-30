# Content moderation

A FastAPI service screens uploaded and generated images and videos. A fake provider stands in for the classifier. React is one page: submit media, and a review list for workspace admins. `docker compose up` starts Postgres, Redis, the provider, the API, two workers, the scheduler, and the page.

Callers are headers, not logins: `X-User-Id` and `X-Workspace-Id`. Seeded workspaces are `ws_verified` (`admin_v`, `member_v`) and `ws_unverified` (`admin_u`, `member_u`).

## Failure

During a provider outage the broken handler treated a timeout as a pass. Uploads went live with no row in `screening_decisions`. A video that was explicit only in a later frame was published in an unverified workspace, because only the first 8 frames were sent. A generation prompt asking for a 16-year-old was accepted. Two workers could both call the provider for the same job. Moderators saw "Nothing to review" when the review request had failed.

A job marked `succeeded` was not proof the media had been screened. In the broken outage the timeout path set `published` and `succeeded` together and wrote no provider decision.

## Evidence

The broken incident tests are in `backend/evidence/broken-pytest.txt`. Five tests failed, five passed:

- a timeout left the item in a state other than held or pending
- frame 9 of an unverified video was published instead of blocked
- a 16-year-old prompt returned 202 instead of 422
- a second worker made a second provider call
- a review database error returned 200 and an empty list instead of 503

The same file shows the checks that already held: an empty review list is 200, another workspace gets 404, an unsigned callback is 401, a member approve is 403, and a score from 0.5 up to 0.8 is held.

The page bug is in `frontend/evidence/broken-review-tests.txt`. Four tests failed because a failed review request was shown as "Nothing to review". `frontend/evidence/fixed-review-tests.txt` records 27 passed after that split.

The workload numbers below are copied from `backend/evidence/`.

## Fix

`SCREENING_MODE=fixed` is the default.

- A timeout, 429, 500, or malformed body does not publish. Each kind has its own retry limit. After the limit the job is `parked` and the media is `held` with `hold_reason` `no_decision`. That hold is not in the human review list, and approve or reject on it returns 409.
- When one parked job later receives a real score, the other parked jobs are released and screened again. Nobody has to approve them.
- Every frame is sent. `explicit` of 0.8 or more is blocked in an unverified workspace.
- A generation prompt is checked before the row is saved. The text is lowercased and hyphens become spaces. A match returns 422 and `{"reasons":[...]}`.
- A worker claims a job with one update and a lease. A second worker gets no row and does not call the provider. If the worker dies, the lease expires and the scheduler queues the job again.
- The review page has three states: loading, failed (with the status and Try again), and genuinely empty.

Workers pop one id from one workspace list, then one from the other. Videos and images in the same workspace share one list. A burst of videos on `ws_unverified` does not keep images on `ws_verified` behind that whole burst.

## Before and after

Same shape of workload: 200 videos from `ws_unverified` and 5 images from `ws_verified`. The first JSON line in each outage file is during the outage. The second is after the provider was turned back on.

Broken outage, `backend/evidence/workload-broken-outage.txt`:

| | published unchecked | calls per upload | oldest waiting (seconds) |
| --- | --- | --- | --- |
| During | 66 | 0.33 | 24 |
| After | 68 | 1.00 | 0 |

The images were already `published` while videos were still pending. The final 0 waiting time is a bad sign. Those jobs were marked `succeeded` without a provider decision, so the wait disappeared from the number.

Fixed outage, `backend/evidence/workload-fixed-outage.txt`:

| | published unchecked | calls per upload | oldest waiting (seconds) |
| --- | --- | --- | --- |
| During | 0 | 0.33 | 34 |
| After | 0 | 1.33 | 0 |

The images were `held` while all 200 videos were still pending. Nothing was published unchecked. After recovery the waiting age fell to 0 because the jobs had been scored. Calls per upload moved above 1 because of the failed tries plus a real score.

A later hand run that waited until every fixed job had parked, then turned the provider on, finished at about 4 calls per upload: three timeouts and one real score. `published_unchecked` stayed 0. `oldest_waiting_seconds` stays large only while a job is not `succeeded`. Read it before turning the provider back on.

With the provider healthy, both modes in `workload-broken-normal.txt` and `workload-fixed-normal.txt` show 0 published unchecked, 1 call per upload, and 0 oldest waiting. The difference is the video rule. In the broken normal run the unverified videos can publish because the last frame is never sent. In the fixed normal run those videos are `blocked`. The images reached `published` within about 30 seconds while videos were still pending.

`backend/evidence/fixed-pytest.txt` records 46 passed. Retry, crash, fairness, and metrics tests were added after that file was saved. The crash tests are `backend/tests/test_crash.py`.

## Remaining limits

The prompt check is a word list. It refuses `a 16-year-old at the beach` and it also refuses `a minor detail`. It misses paraphrases, other languages, and split words.

The crash test raises inside the worker after a scored reply and before the save. The hand kill stops the worker during an 8 second provider delay, which is before the answer. Neither one is a disk crash. Recovery calls the provider again, so a lost save is billed twice. The goal is one successful save, not one HTTP call when the first result was thrown away.

Provider call counts live in that process. Restarting it clears them. Truncating Postgres does not.

Two workers and a one-row scheduler probe are enough for the exercise. They are not sized for a large outage.

## Time spent

Around 7 hours spent on this.

## Part 3

### Production Moderation Strategy

### 1. Moderation Approach and Cost

I'd go with a hybrid approach initially. Using a paid moderation API for visual checks is simpler and more cost-effective than maintaining dedicated GPUs at this scale.

- **CSAM detection:** Use a dedicated hash-matching service to check known CSAM content before processing anything else.
- **Visual moderation:** Send every image and video frame to a moderation API. It needs to cover all the required categories: minors, sexual violence, bestiality, self-harm, non-consensual real-person imagery and explicit content.
- **Human review:** Anything falling into a borderline range should go into the review queue instead of being automatically approved.
- **Failure handling:** If the moderation provider is down, times out or returns an invalid response, keep the media on hold. Nothing should be published without a successful moderation decision.

For videos, I'd check all 60 frames of a one-minute video rather than sampling just a few frames. This avoids missing explicit or prohibited content appearing towards the end.

**Estimated monthly cost:**

Assuming a moderation API charges around $1 per 1,000 image checks:

- 10,000 images = $10
- 1,000 videos × 60 frames = $60
- **Total = approximately $70/month**

I'd budget around $80–100 to account for retries and additional overhead. These are rough estimates, not actual vendor quotes. Some providers also offer video-based pricing, which could make it cheaper.

At this volume, I don't see much benefit in maintaining our own GPU infrastructure. I'd revisit self-hosted models once the volume increases enough to justify the additional infrastructure and maintenance.

### 2. Generation Prompt Moderation

Prompts should be checked before they reach the generation service.

I'd use a combination of keyword/pattern matching and a lightweight text classifier. Keyword matching catches obvious requests, while the classifier helps identify prompts that try to describe prohibited content indirectly.

I'd also normalize prompts to catch common bypass attempts, such as misspellings, spacing tricks and obfuscated words.

One important thing is to check the final prompt as well, especially if another AI step rewrites or enhances it. A prompt that passes the initial check shouldn't automatically be trusted after modification.

If a prompt is clearly prohibited, reject it. If the result is uncertain, send it for further review rather than allowing generation.

### 3. CSAM Hash Matching

I'd integrate a dedicated hash-matching service, such as a trusted PhotoDNA-based service, into the upload pipeline.

The idea is to generate a perceptual hash and compare it against a database of known prohibited content before sending the media for normal moderation.

If there's a match, block the content and follow the appropriate reporting and escalation procedures.

If the hash-matching service becomes unavailable, uploads should remain on hold until the check can be completed. We shouldn't bypass this check just because an external service is down.

Generated content should go through the same applicable safety checks before becoming available.

### 4. Scaling to 1 Million Uploads a Day

At this scale, I'd expect the moderation queue and external provider rate limits to become the first bottlenecks. Database throughput and worker capacity would also need attention.

The first things I'd monitor are:

- Queue depth and age of the oldest pending job.
- Provider response times, errors and rate limits.
- Number of retries and failed moderation attempts.
- Worker throughput and resource usage.
- Database query latency and connection usage.
- Average time from upload to final moderation decision.

My first changes would be to:

- Separate image and video queues so large video workloads don't delay image moderation.
- Scale workers horizontally based on queue depth and processing time.
- Introduce provider-aware rate limiting and exponential backoff for retries.
- Improve database performance and archive older job records where appropriate.
- Add alerts for growing queues, provider failures and unusual processing delays.

I'd also evaluate self-hosted models for workloads where they make financial sense, while keeping specialized detection services for categories that need them.

The main priority wouldn't change with scale: media must pass all required safety checks before it can be published.

## Production plan

### First 15 Minutes

First, I'd check whether the problem is coming from the moderation provider or something in our own application.

The immediate priority would be to stop any new media from being published without a successful moderation result. I'd also check what was published during the outage without being screened and take it offline until it passes moderation.

Next, I'd check how many jobs are waiting in the queue and how long the oldest one has been waiting. Items without a moderation decision should never be available for manual approval.

I'd also collect the provider's call statistics before restarting anything, as they could help identify what happened and whether duplicate requests were made.

### Rollout

I'd move the changes through dev, staging and then production.

In dev, I'd run the incident regression tests, including provider timeouts, duplicate jobs, invalid callbacks and workspace isolation. I'd also make sure the review page handles failed requests correctly.

In staging, I'd use the same setup as production and simulate a provider outage. I'd verify that media stays on hold during the outage and gets screened automatically once the provider is back.

For production, I'd enable the new behavior for one workspace first. I'd monitor the queue, provider calls and published unchecked media. If everything looks good, I'd enable it for the remaining workspaces.

Media held during the outage should be screened again automatically. We should never bulk-approve it just to clear the queue.

### Rollback

If something fails in dev or staging, I'd fix it before moving the changes to production.

In production, if workers stop processing jobs, the claim process starts failing or media keeps getting stuck despite a healthy provider, I'd roll back the affected workspace to the previous fixed version.

I'd roll back the workers and scheduler together and leave other workspaces unaffected if they're still working correctly.

One thing I wouldn't do is return to the old behavior where a provider timeout allows media to be published. That's what caused the original incident in the first place.

If the initial rollout works, I'd continue enabling the changes for the remaining workspaces. If problems appear during the wider rollout, I'd stop it and move the affected workspaces back to the previous fixed version.

### How I'd Verify Recovery

I'd consider the issue resolved when:

- `published_unchecked` stays at 0 for all media created after the fix.
- `oldest_waiting_seconds` starts decreasing as jobs receive successful moderation decisions.
- Media held during the outage gets screened automatically once the provider recovers.
- Provider calls return to roughly one per upload during normal operation. They may be higher during an outage because of retries.
- Images from one workspace continue getting processed even when another workspace has a large video backlog.
- The review page shows an actual error when the request fails instead of displaying an empty queue.

The important thing is that a job should only be marked as completed after a valid moderation decision has been received and saved. A timeout or failed request should never count as a successful screening.
