# Klippo — Product Prompt Quality Checklist

**Audit date:** 18 October 2026  
**Repository:** `nurynayreen88/TransisiVideoBot`  
**Base commit reviewed:** `d8fc4288bed49b7a9a19cd9d61d43e07e82e33a8`  
**Master library:** `prompts/prompt_library.json` — 1,171 prompts across 19 categories  
**Important:** This is a triage checklist, not a claim that all 1,171 prompts have passed a human quality review. Three shoe overrides and six handbag overrides have been specifically rewritten, structurally checked, and merged as additive quality improvements. Their actual generated video output still needs visual inspection. The master library remains unchanged.

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
| Beg / Bags | 64 | IN PROGRESS — 9 prompts text-audited | Six additional ID-preserving overrides are merged; continue reviewing the remaining prompts. Visual generation test still pending. |
| Dompet / Wallets | 59 | BASELINE OK — deeper review pending | Check opening/closing hinges, card slots only if visible, hand interaction and scale consistency. |
| Kasut / Shoes | 62 | PASS for 3 named overrides; remaining prompts NOT AUDITED | Review the other 59 prompts for shoe-specific actions, footwear geometry and plausible foot contact. |
| Kosmetik & Kecantikan / Beauty | 70 | BASELINE OK — deeper review pending | Check applicator/product compatibility, believable liquid/cream behaviour, packaging continuity and avoid unsupported skin/health claims. |
| Gajet & Elektronik / Gadgets | 63 | BASELINE OK — deeper review pending | Check ports/buttons/screens match the named device; no invented UI, impossible connections or unsupported technical claims. |
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

