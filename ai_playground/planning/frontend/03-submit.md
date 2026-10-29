# Phase 3 — Submit

Phase 2 must already pass. Do this phase only. Stop at the end.

## Goal

The person can send an upload or a generation and see the status the API returns. The page polls the one new id. It does not decide the status itself.

## Do not

- Do not add the review box.
- Do not compute 0.5 or 0.8 in the component. The example buttons only fill the text box.

## Examples

`src\domain\examples.ts` exports four strings. Buttons fill the frame box with these. The person can still edit the box.

| Button text | What it fills |
| --- | --- |
| `Safe image` | `{"type":"image","source":"upload","frames":[{"explicit":0.1}]}` |
| `Explicit image` | `{"type":"image","source":"upload","frames":[{"explicit":0.95}]}` |
| `Needs review` | `{"type":"image","source":"upload","frames":[{"self_harm":0.66}]}` |
| `Video, last frame explicit` | A video with 9 frames. The first 8 are `{"explicit":0.01}`. Frame 9 is `{"explicit":0.95}`. `source` is `upload`. |

A `<select>` labeled `How`, with values `upload` and `generation`. When it is `generation`, show a text input labeled `Prompt`, with default text `two adults on a beach at sunset`.

At submit time, a pure function `buildMediaBody(parsedJson, how, prompt)` in `src\domain\mediaBody.ts` builds the body:

- `generation`: set `source` to `generation` and `prompt` to the input text.
- `upload`: set `source` to `upload` and delete any `prompt` key. The backend refuses an upload that carries a prompt (`422` `upload_has_no_prompt`), so switching back to upload must not leave one behind.

The person never edits `source` or `prompt` by hand.

If the frame box is not valid JSON, or it has no `frames` array, do not call the API. Show `Could not read the JSON`.

## Submit behavior

`src\components\SubmitForm.tsx`. It receives `client` and `caller` as props. `App` creates the client once with `createClient()` and passes it down to the form and to the review box. Tests pass a fake client object with the same methods.

- Button `Submit`.
- On click, one `postMedia`.
- `202`: show `Accepted <id>` and status `pending`. Then call `getMedia` for that id every 1 second, at most 20 times, until `status` is not `pending`. Show the latest status and the `reasons` joined by commas.
- Still `pending` after 20 tries: stop polling and show `Still pending`. During a provider outage this is normal. Retries can take longer than 20 seconds. Do not show it as an error, and do not show it as published.
- A `getMedia` failure during polling: show `Status check failed <status>` and stop polling.
- Stop polling when the component unmounts or the caller changes. Clear the timer in the effect cleanup.
- `422`: show `Refused` and the reasons. Do not poll.
- Any other failure: show `Submit failed` and the status. Do not poll.
- A second click while a poll is running is ignored.

Log `step=submit` with `media_id` and `status` when the first response returns. Do not log the frames.

The poll is one id. It is not a loop over a list.

## Tests

Mock the client. Do not use real `fetch` in these tests. Pass a fake client into the form so the test does not depend on timers plus the network.

| Test | Assert |
| --- | --- |
| `test_refused_prompt_does_not_poll` | `postMedia` returns `422` with reasons `["minor"]`. The page shows `Refused` and `minor`. `getMedia` was not called. |
| `test_accepted_then_published` | `postMedia` returns `202` and an id. The first `getMedia` returns `pending`. The second returns `published`. The page shows `published`. `getMedia` was called with that id only. |
| `test_bad_json_does_not_call` | Frame box is `not json`. Click submit. `postMedia` was not called. The page shows `Could not read the JSON`. |
| `test_safe_image_button_fills_the_box` | Click `Safe image`. The text box contains `"type": "image"` or `"type":"image"`. |
| `test_still_pending_after_twenty_tries` | Every `getMedia` returns `pending`. After 20 polls, the page shows `Still pending` and `getMedia` is not called a 21st time. |
| `test_upload_body_has_no_prompt` | In `src\domain\mediaBody.test.ts`. Unit test of `buildMediaBody`. A parsed body that already has `prompt`, with how `upload`, comes back with no `prompt` key and `source` `upload`. |
| `test_generation_body_has_prompt` | Same file. How `generation` sets `source` and the given prompt. |

Use `vi.useFakeTimers()` for the poll, and advance one second at a time with `vi.advanceTimersByTimeAsync(1000)`. Create the user with `userEvent.setup({ advanceTimers: vi.advanceTimersByTime })`, or clicks will hang under fake timers. Call `vi.useRealTimers()` at the end of the test.

## Done when

- `npm test` passes.
- The form does not contain the number `0.8`.
- One submit causes one `postMedia`.

## Report, then stop

```text
Phase 3 done.
Files affected:
- <full path of every file created or edited>
Tests: npm test
Result: <pass or fail>
```
