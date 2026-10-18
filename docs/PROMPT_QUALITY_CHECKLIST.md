# Klippo — Product Prompt Quality Checklist

**Audit date:** 18 October 2026  
**Repository:** `nurynayreen88/TransisiVideoBot`  
**Base commit reviewed:** `d8fc4288bed49b7a9a19cd9d61d43e07e82e33a8`  
**Master library:** `prompts/prompt_library.json` — 1,171 prompts across 19 categories  
**Important:** This is a triage checklist, not a claim that all 1,171 prompts have passed a human quality review. Three shoe overrides, nine handbag overrides, one beauty override and one gadget override have been specifically rewritten or reviewed, structurally checked, and merged as additive quality improvements. Their actual generated video output still needs visual inspection. The master library remains unchanged.

## Status legend

- **PASS — reviewed:** Prompt-specific improvement was made and structural checks passed.
- **BASELINE OK — deeper review pending:** The library entry has core structural elements (duration/format, storyboard, product-fidelity language by the initial scan), but the actions, realism, category fit, and originality still need a prompt-by-prompt review.
- **REVIEW FLAG:** A phrase-based scan did not find a commonly used product-lock or no-text phrase. This is a manual review flag, not proof that the prompt is defective; it may use different wording.
- **NOT AUDITED:** No evidence of a completed, prompt-by-prompt quality sign-off yet.

## 1. Specifically improved and checked

- [x] `shoes_on_feet_walk_v1` — **On-Foot Walk Test**: realistic steps, grounded foot contact, consistent shoe shape and no unsupported performance claims.
- [x] `shoes_clean_product_reveal_v1` — **Clean Product Reveal**: restrained studio reveal, product remains grounded, no invented packaging/accessories.
- [x] `shoes_lace_and_step_v1` — **Lace-Up & First Steps**: fastening action is conditional on the shoe actually having laces; removed unrelated study-desk/books context.
- [x] Existing IDs retained; the three prompts are stored as additive overrides rather than rewriting the master library.
- [x] GitHub Actions validation passed for PR #53 before merge.
- [x] Master library kept at 1,171 entries; the reviewed library blob was unchanged.
- [ ] Test these three prompts against representative product images in the actual video-generation flow. Repository checks are not a substitute for a visual generation test.

## 2. Category-by-category checklist

**Reading this table:** “Baseline structure” means the prompt entries have a storyboard with four shots and the initial scan found duration/format markers. It does **not** mean every action has been manually judged realistic or product-specific.

| Product category | Prompts | Current status | Next quality check |
|---|---:|---|---|
| Pakaian / Clothing | 63 | BASELINE OK — deeper review pending | Check fabric movement, fit, drape, body anatomy, hijab/clothing continuity and avoid changing garment design. |
| Beg / Bags | 64 | IN PROGRESS — 18 ID-preserving overrides merged across bags, shoes, beauty, gadgets, wallets and hijab | Continue reviewing remaining prompts and category variation. Visual generation tests still pending. |
| Dompet / Wallets | 59 | BASELINE OK — deeper review pending | Check opening/closing hinges, card slots only if visible, hand interaction and scale consistency. |
| Kasut / Shoes | 62 | PASS for 4 named overrides; remaining prompts NOT AUDITED | Review the other 58 prompts for shoe-specific actions, footwear geometry and plausible foot contact. |
| Kosmetik & Kecantikan / Beauty | 70 | PASS for 1 named override; remaining prompts NOT AUDITED | Check applicator/product compatibility, believable liquid/cream behaviour, packaging continuity and avoid unsupported skin/health claims. |
| Gajet & Elektronik / Gadgets | 63 | PASS for 1 named override; remaining prompts NOT AUDITED | Check ports/buttons/screens match the named device; no invented UI, impossible connections or unsupported technical claims. |
| Barangan Rumah / Home | 62 | BASELINE OK — deeper review pending | Check the product is used for its actual purpose, object contact and before/after changes are plausible. |
| Jam & Aksesori / Accessories | 62 | BASELINE OK — deeper review pending | Check jewellery drape, watch fit, glasses placement, reflections and correct scale. |
| Makanan & Minuman / Food | 62 | BASELINE OK — deeper review pending | Check believable texture, pouring, serving and packaging; no sudden shape/quantity changes or unsupported claims. |
| Alat Tulis & Keperluan Belajar / Stationery | 62 | BASELINE OK — deeper review pending | Check writing/grip/contact, stationery-specific actions and avoid irrelevant props or garbled readable text. |
| Sukan & Aktiviti Luar / Sports | 62 | BASELINE OK — deeper review pending | Check equipment is used correctly and safely; no invented performance benefits or physically impossible motion. |
| Travel & Bagasi / Travel | 60 | BASELINE OK — deeper review pending | Check luggage wheels/handles, packing actions, scale and continuity of items. |
| Haiwan Peliharaan / Pets | 60 | BASELINE OK — deeper review pending | Check animal behaviour and interactions are calm, plausible and safe; keep the product clearly featured. |
| Aksesori Kereta / Automotive | 60 | BASELINE OK — deeper review pending | Check correct placement/use, safe stationary demonstrations and compatibility is not invented. |
| Berkebun & Tanaman / Garden | 60 | BASELINE OK — deeper review pending | Check watering, soil, plant and tool actions behave naturally; avoid impossible liquid/plant transformations. |
| Dapur & Peralatan Masak / Kitchen | 60 | BASELINE OK — deeper review pending | Check lids, handles, pouring, stirring and food-contact actions; avoid unsupported heat/material claims. |
| Perabot & Dekorasi / Furniture | 60 | BASELINE OK — deeper review pending | Check weight, contact, doors/drawers, reflections and room geometry remain stable. |
| Bayi & Keperluan Anak / Baby | 60 | BASELINE OK — deeper review pending | Check safe product handling, age-appropriate use, stable assembly and no unsafe baby interaction. |
| Seni & Kraf / Crafts | 60 | BASELINE OK — deeper review pending | Check tool/material interactions (threading, painting, crochet, beads) and keep counts/shapes consistent. |

## 2A. Bags audit — batch 1 (text-level review)

**Scope:** First three dedicated handbag prompts in the master library. This is a prompt/storyboard review only; no generated video was available for visual inspection.

- [x] `bags_handheld_showcase_v1` — **Handbag Showcase**: whole-bag reveal, one restrained lift/steadying action, one visible-detail close-up, stable hero finish. Handle/strap physics and product-lock rules are appropriate.
- [x] `bags_luxury_closeup_v1` — **Luxury Detail Close-Up**: anchored full-bag view, one controlled macro pass, existing hardware only when present, full-product return. Avoids unsupported material claims and artificial texture.
- [x] `bags_daily_carry_v1` — **Everyday Carry**: grounded bag setup, one plausible pickup, one natural carry/step, steady finish. Correctly avoids assuming a shoulder strap for a hand-held clutch.
- [x] All three contain four timed storyboard shots matching the prompt's action sequence; product continuity and no-text/logo/watermark constraints are present.
- [x] **Decision:** No text-level rewrite required for these three entries; their existing instructions are already specific and coherent. No IDs or master-library entries were changed.
- [ ] Generate representative clips and visually inspect handle/strap stability, hands, bag geometry, shadows and final-frame continuity before claiming end-to-end PASS.

**Next small batch:** `bags_tabletop_pickup_v1`, `bags_office_storyboard_v1`, and `bags_editorial_flatlay_v1`. Check for generic template wording, action/storyboard agreement and category-specific realism.

## 2E. Beauty and gadget prompt audit — two more ID-preserving overrides

- [x] `beauty_texture_demo_v1` — reference-led packaging, conditional application, natural texture, no unsupported beauty/health claims, and a stable final hero frame.
- [x] `gadgets_real_use_demo_v1` — one evidence-supported interaction, faithful controls/ports/screens, realistic finger contact, and no invented specifications or interface.
- [x] Both prompts retain the existing IDs and four timed shots; repository validation passed on PR #66 before merge.
- [ ] Generate representative clips and visually inspect packaging/hand contact, geometry, screen behaviour and final-frame continuity.

## 3. Automated structural audit — current snapshot

- [x] Master library parses as JSON.
- [x] **1,171** prompt entries and **19** categories found.
- [x] No duplicate prompt IDs detected.
- [x] No missing category references or orphan prompt entries detected.
- [x] Every library entry has a four-shot storyboard in the current snapshot.
- [x] Duration/vertical-format markers found across the library by the initial scan.
- [ ] Manual quality review of each prompt's action sequence.
- [ ] Cross-check each prompt against its storyboard so they describe the same action.
- [ ] Check product-specific realism and whether each concept differs meaningfully from neighbouring prompts.
- [ ] Run representative image-to-video tests and inspect the resulting clips.
- [ ] Confirm short enough output for Telegram and the actual generation flow.

## 4. Phrase-based flags that need manual inspection

The initial scan found a small number of prompts that did not contain the exact common phrases used by the scanner. Different wording may already cover the requirement, so do not automatically rewrite these without reading the complete prompt.

| Category | Flag | Count |
|---|---|---:|
| Pakaian / Clothing | Common no-text phrase not detected | 1 |
| Beg / Bags | Common no-text phrase not detected | 3 |
| Dompet / Wallets | Common no-text phrase not detected | 1 |
| Gajet & Elektronik / Gadgets | Common no-text phrase not detected | 1 |
| Kasut / Shoes | Common product-lock phrase not detected | 4 |
| Kosmetik & Kecantikan / Beauty | Common product-lock phrase not detected | 1 |

**Priority:** Inspect these flags manually first, then audit the other prompts. These are scanner flags, not confirmed defects.

## 5. Main quality risks to check next

- [ ] **Template repetition:** Each category contains many `klippo_*_batch2` through `batch6` entries. The names suggest camera/lighting variants; review whether the *actual product action* changes meaningfully, not just the camera angle.
- [ ] **Action-category mismatch:** Ensure a prompt for one product type does not introduce unrelated props/actions from another category.
- [ ] **Storyboard consistency:** Each shot in the prompt text must match the structured `storyboard` array.
- [ ] **Realism:** Avoid floating products, morphing geometry, impossible hands/feet, inconsistent reflections, and abrupt changes.
- [ ] **Product truth:** No invented material, size, compartment, feature, branding, certification, performance or health claim.
- [ ] **10-second clarity:** Keep a readable four-shot sequence and avoid contradictory instructions or excessive prompt length.
- [ ] **Output restraint:** No unwanted on-screen text, captions, added logos or watermarks.

## 6. Recommended audit order

1. [ ] **Bags** — revisit the originally requested handbag quality pass and sign off the category.
2. [ ] **Shoes** — review the remaining shoe prompts after the three improved entries.
3. [ ] **Beauty and gadgets** — product interactions and geometry are especially sensitive.
4. [ ] **Clothing and accessories** — body/object fit, drape and reflections.
5. [ ] **Food and kitchen** — liquids, food textures and object interactions.
6. [ ] **Home, furniture, travel, automotive and garden** — realistic use and contact.
7. [ ] **Stationery, sports, pets, baby and crafts** — category-specific action and safe use.
8. [ ] Review the repeated batch prompts across all categories for meaningful variation.

**Rule for marking a category PASS:** Do not mark the whole category as good because its JSON structure passes. Mark it only after its prompts have been reviewed for category-specific action, visual continuity, realistic motion, product fidelity, non-repetitive concepts and consistency between prompt text and storyboard. Record reviewed IDs and test evidence as work progresses.

## 2D. Handbag prompt audit — six additional ID-preserving overrides

**Current-main follow-up:** These six reviewed overrides have been carried forward onto the current `main` baseline so they include the latest White Doodle and duration changes. The master prompt library remains unchanged; the overrides are additive.

- [x] `bags_everyday_carry_v1` — realistic supported pickup, measured carry and controlled finish.
- [x] `bags_tabletop_hero_v1` — camera-led reveal while the bag remains supported and stationary.
- [x] `bags_sling_crossbody_v1` — crossbody wearing is conditional on the visible bag design; strap attachment and placement stay consistent.
- [x] `bags_tabletop_pickup_v1` — tabletop opening, plausible pickup and controlled set-down.
- [x] `bags_office_storyboard_v1` — clear ready-to-leave sequence with a natural lift and short carry.
- [x] `bags_editorial_flatlay_v1` — stationary bag with camera movement; close-ups only of details actually visible.
- [x] Each override defines four timed shots across exactly 10 seconds and aligns the written prompt with the storyboard.
- [x] Original IDs and the master library are preserved; only the additive override file changes for these prompts.
- [x] CI passed against the current `main` baseline before merge.
- [ ] Visually inspect generated clips for handle/strap physics, hand contact, product geometry, contact shadows and final-frame continuity. Text/CI review is not a visual-generation PASS.

**Quality rule:** Do not infer hidden compartments, material, capacity, durability, brand marks or features from a generic bag name. Keep actions conditional where the product's visible design is not known.


## 2E. Handbag storyboard-alignment batch

- [x] `bags_handheld_showcase_v1` — four shot directions embedded verbatim; realistic supported handling and stable hero finish.
- [x] `bags_luxury_closeup_v1` — macro details limited to visible features; no unsupported material claims.
- [x] `bags_daily_carry_v1` — natural carry action, consistent scale and conditional handling method.
- [x] Existing prompt IDs and master library preserved; additions are ID-preserving overrides.
- [ ] Run CI on this batch before merging.
- [ ] Inspect generated clips for physical handling, product geometry and final-frame continuity; text checks are not visual validation.

## 2F. Beauty, gadget and wallet prompt-quality batch

- [x] `beauty_texture_demo_v1` — product texture/application remains conditional on visible evidence; no unsupported cosmetic or skin claims.
- [x] `gadgets_real_use_demo_v1` — one plausible action; no invented interface, ports, specifications or outcomes.
- [x] `wallets_luxury_macro_v1` — camera-led macro detail; no inferred materials or hidden construction.
- [x] Four-shot timings and storyboard directions are embedded verbatim; no-on-screen-text rules are explicit.
- [ ] Run CI against current `main` before merge.
- [ ] Visually inspect generated clips; structural checks are not a visual-quality pass.

## 2G. Shoe, hijab and wallet storyboard-alignment batch

- [x] `shoes_running_shoe_motion_v1` — running action is conditional on worn/reference context; no unsupported performance claims.
- [x] `clothing_hijab_drape_v1` — preserve wrap, coverage, folds and colour; avoid unsupported repositioning.
- [x] `wallets_open_close_v1` — opening is conditional on visible construction; open/closed state remains continuous.
- [x] Four-shot directions are embedded verbatim with the required 10-second timing and explicit no-on-screen-text rules.
- [ ] Run CI against current `main` before merge.
- [ ] Visually inspect generated clips; structural checks do not prove visual quality.


## 2H. Running-shoe prompt concision pass

- [x] `shoes_running_shoe_motion_v1` — shortened the opening rules by 206 characters while retaining the existing ID and all four storyboard directions verbatim.
- [x] Exact 10-second timing remains `0–2s`, `2–6s`, `6–8s`, `8–10s`; the master library is unchanged.
- [ ] Generated-video visual inspection is still pending; this text-only change is not a visual quality PASS.


## 2I. Premium HD and Shopee/TikTok delivery consistency — batch 1

- [x] Added a shared delivery-quality specification to all 18 existing ID-preserving quality overrides.
- [x] Added the same baseline to both prompt-engine output paths so ordinary storyboard prompts and library-style prompts request highest native quality, target 1080x1920 vertical 9:16, crisp visible detail, natural colour/exposure, low noise and stable frame-to-frame geometry.
- [x] Explicitly targets Shopee and TikTok full-screen mobile viewing, with the product kept inside a central safe area.
- [x] Added safeguards against blur, compression artefacts, oversharpening, flicker, platform UI, unrequested captions, claims, logos and watermarks.
- [x] Existing prompt IDs, the 1,171-entry master library and video engine/provider are unchanged.
- [ ] Run repository CI and inspect actual generated clips at native output resolution; prompt wording cannot guarantee the video model's final resolution or fidelity.
- [ ] Continue prompt-by-prompt action/storyboard review of the remaining master-library entries in small batches.

**Scope note:** This batch standardizes the delivery brief; it does not mark all 1,171 master prompts as individually audited or visually verified.


## 2J. Category-specific realism and storyboard batch 2

- [x] Added ID-preserving overrides for `fashion_walking_ootd_v1` — natural walking pace, fabric physics, true fit and a readable full-outfit finish.
- [x] Added ID-preserving overrides for `fashion_mirror_selfie_v1` — mirror, phone and reflection actions are conditional on reference support; avoids invented props and reflection mismatch.
- [x] Added ID-preserving overrides for `beauty_vanity_hero_v1` — no assumption that every beauty item is liquid, has an applicator, or should be opened/applied.
- [x] Added ID-preserving overrides for `gadgets_detail_reveal_v1` — visible hardware only; no invented ports, interface, lights or powered-on state.
- [x] Added ID-preserving overrides for `wallets_clean_flatlay_v1` — preserves construction; does not add cash/cards, open the wallet, or imply hidden capacity.
- [x] Added ID-preserving overrides for `shoes_side_profile_reveal_v1` — grounded shoe geometry; no forced wearer, unnatural foot twist, or unseen sole detail.
- [x] All six use four matching timed shots (0–2s, 2–6s, 6–8s, 8–10s), a consistent product-lock section and HD vertical 9:16 delivery guidance for Shopee and TikTok.
- [x] Existing IDs preserved; changes are additive in `prompt_quality_overrides.json`; master library remains unchanged at 1,171 prompts across 19 categories.
- [ ] Run repository CI before merging.
- [ ] Visually inspect generated clips; text and CI validation do not prove external video output is realistic or truly HD.

**Scope note:** This batch covers six named prompts only. It does not mark the clothing, beauty, gadget, wallet or shoe categories fully audited.


## 2K. Product, human, environment and audio integrity — batch 3

- [x] Added ID-preserving overrides for `kitchen_lunchbox_v1`, `kitchen_cookware_v1`, `kitchen_spice_rack_v1`, `kitchen_cutting_board_v1`, `kitchen_tumbler_v1`, and `kitchen_appliance_v1`.
- [x] Added explicit anti-defect constraints for product geometry/parts, hand anatomy, continuity of people and backgrounds, plausible reflections/contact shadows, food/liquid physics, focus and temporal stability.
- [x] Avoided unsupported product features, labels, compartments, accessories, claims and operating states. Physical actions are conditional on the visible product; use a camera move when unsupported.
- [x] Audio default is no voice-over; if speech is explicitly requested, require one consistent natural voice, clear pronunciation, stable accent, clean levels and no clipping/echo/repeated words or voice changes.
- [x] All six use four timed beats totalling exactly 10 seconds and include 1080x1920 vertical 9:16 guidance for Shopee and TikTok.
- [x] Master prompt library and existing IDs remain unchanged; changes are additive in the quality override file.
- [ ] Run repository CI before merging.
- [ ] Generated video/audio still needs visual and listening review; prompt constraints reduce risk but cannot guarantee every model render is defect-free.

**Scope note:** This batch covers six kitchen prompts only. It does not mean the full kitchen category or all 1,171 master prompts have been individually verified.


## 2L. Adult model, face, wearable product and background continuity — Batch 4

- [x] Added six ID-preserving quality overrides for garment detail, sit-to-stand outfit reveal, walk-past camera, beauty hand swatches, jewellery on model and sunglasses try-on.
- [x] Locked adult model identity and anatomy across frames: consistent face/body/hair/skin, plausible hands and joints, grounded foot contact, no duplicated limbs, fused fingers or face morphing.
- [x] Locked garment/accessory geometry and visible details: no changing cut, print, frame shape, lens tint, stone/link count, invented materials, extra accessories or unsupported product claims.
- [x] Added scene continuity rules for stable background, light direction, reflections, contact shadows and focus; no flicker, texture crawl, focus pumping or abrupt exposure changes.
- [x] All six use four timed beats totalling exactly 10 seconds and include 1080x1920 vertical 9:16 guidance for Shopee and TikTok, with the subject inside the central safe area.
- [x] Audio defaults to no voice-over; if speech is requested, one consistent natural voice, clean levels and accurate lip-sync are required.
- [x] Master prompt library and existing IDs remain unchanged; the six updates are additive overrides only.
- [ ] Run repository CI before merging.
- [ ] Generated videos still require visual review and any requested speech requires listening review; prompt constraints reduce risk but cannot guarantee every model render is defect-free.

**Scope note:** This batch covers six selected fashion/beauty/accessory prompts only, not every prompt in those categories or the full 1,171-prompt library.


## 2M. Strict no-added-logo rule — platform-wide

- [x] Added a shared no-added-logo instruction to the prompt engine so generated prompt modes explicitly prohibit TikTok, Shopee, creator, AI-generator and provider logos/watermarks, corner bugs, end cards, branded borders, platform UI and background signage.
- [x] Added the rule to every existing quality override prompt without changing prompt IDs or deleting master-library entries. Kept the original storyboard shot directions intact so they remain exactly embedded in the corresponding prompt.
- [x] Clarified product fidelity: a mark already physically printed on the supplied product may remain only as part of that product; never duplicate it as a separate overlay or enlarge it.
- [ ] Run repository CI before merging.
- [ ] Confirm actual generated clips visually after deployment; prompt-level rules cannot guarantee every external video model will obey them.

**Scope note:** This change covers all current quality overrides plus the shared prompt engine. It does not claim that video outputs have been rendered and visually verified.


## 2N. Expanded product-background choices

- [x] Expanded the Telegram product-background menu with eight additional solid colour studios: navy, sage, sky blue, lavender, rose, mint, terracotta and charcoal.
- [x] Added six additional premium gradients: sky, lavender, sage, blush, midnight and sand.
- [x] Kept the existing original, white, beige, dark, pastel, cream gradient, subtle pattern, duotone, mist and custom-image options.
- [x] Updated both the bundled bot background engine and the standalone `product_background.py` module, including the premium animated-studio palette and accepted callback values.
- [ ] Run CI and syntax checks before merging.
- [ ] Verify menu display and rendered output in the live bot after a separately authorized deployment.

**Design rule:** Backgrounds are simple, text-free and logo-free, selected to support product visibility rather than distract from the product.
