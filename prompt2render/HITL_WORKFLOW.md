# How to manually repair a specific section using HITL

You can force the Harness to regenerate and rerender any specific section by creating a Human-in-the-Loop (HITL) feedback file. 

The repair router will see your feedback, mark the scene as rejected, and route it back to the Manim generator. Crucially, the Manim generator and renderer plugins are designed to preserve successful sections—they will only regenerate and rerender the specific scene you rejected.

## Step-by-step workflow

1. Open your project folder (e.g., `C:\fdx-studio\projects\History and Definition of Pi`).
2. Create a file named exactly `hitl_feedback.json` in that folder.
3. Add a JSON object where the keys are the two-digit section numbers (e.g., `"01"`, `"04"`) you want to fix.
4. For each section, provide `"status": "reject"` and a `"reason"` that tells the LLM what to change.

### Example `hitl_feedback.json`

```json
{
  "04": {
    "status": "reject",
    "reason": "The text overlaps with the arrows. Move the text label to the top left corner using UP + LEFT."
  },
  "07": {
    "status": "reject",
    "reason": "You drew a square but the narration talks about a circle. Draw a circle instead."
  }
}
```

## Running the repair

After saving the file, run your normal command:

```powershell
python prompt2render.py auto "History and Definition of Pi" --harness --strict --manim
```

### What happens next:

1. The pipeline starts normally.
2. `generator_manim` sees that sections 01, 02, 03, 05, 06, and 08 are already cached and successful, so it **skips generating them**.
3. `renderer_manim` sees the MP4s for the successful sections already exist, so it **skips rendering them**.
4. At the end of the pipeline, the `feedback_hitl` plugin reads your `hitl_feedback.json` file.
5. It emits a `BLOCKING` finding for section 04 and section 07, containing your exact reason.
6. The `repair_router` intercepts this finding and sends sections 04 and 07 back to `generator_manim`.
7. `generator_manim` reads your feedback from the repair context and asks Gemini to rewrite the code for those two sections, specifically instructing it to fix the issues you mentioned.
8. `renderer_manim` rerenders only the new code for sections 04 and 07.
9. The pipeline re-verifies the new videos.
10. **Important:** Once you are happy with the fixed sections, **delete or rename `hitl_feedback.json`**, or change the status to `"accept"`. If you leave it as `"reject"`, the pipeline will keep trying to repair those sections every time you run it.

## The Drop-in Fixes

The attached `Prompt2Render_latest_dropin_v8.zip` contains the updated `feedback_hitl` plugin and `repair_router` policy to ensure this workflow functions correctly in Manim mode. (In the original code, HITL findings were treated as warnings rather than blocking errors, which meant the repair router ignored them).

This package also includes all previous fixes (LLM fallback for semantic verification, captions, alignment, graph conflicts, etc.) based on remote commit `93378b267d6ce3a5ae21f7a670633bdffa188762`.

Copy every file to the matching path in `C:\fdx-studio` before trying the HITL workflow.

— Manus AI
