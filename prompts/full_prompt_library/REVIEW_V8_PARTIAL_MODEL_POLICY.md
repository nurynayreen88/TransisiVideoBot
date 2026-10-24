# V8 partial-model visual policy — review only

Add **PARTIAL_MODEL** as a distinct model-present visual category, alongside FULL_MODEL, HANDS_ONLY, PRODUCT_ONLY and ANIMAL_ONLY. A cropped body is a real model, never product-only. No face is shown in PARTIAL_MODEL. Prefer a model-present scene for practical demonstrations.

## Product-specific framing
- Handbag, shoulder bag, tote: shoulder to hip or shoulder to waist; the real bag is carried naturally on shoulder or in hand. Crop above the mouth and exclude face.
- Shoes: feet and lower legs, optionally to knees, showing natural standing and walking. No face or upper body.
- Wristwatch, bracelet: wrist and forearm with realistic movement and scale.
- Rings: fingers and hand with real-life fit; no face.
- Clothing: crop relevant torso or legs only when fit and product identity remain fully visible. FULL_MODEL remains preferred when the complete silhouette is necessary.
- HANDS_ONLY is reserved for hands and limited forearms demonstrating tactile product use; PARTIAL_MODEL includes a larger relevant body region such as shoulder, waist, legs or feet.

## Voice and duration
PARTIAL_MODEL supports off-camera Malaysian Malay narration or instrumental music only. No visible model speech or lip-sync claims without a visible mouth. The age selection appears only where an actual human model is selected; product-only and animal-only have no model age. Store every valid combination as its own complete 10-second prompt or continuous 20-second two-part prompt; AUDIO is last in each part. Do not place conditional assembly language inside final prompts.

## Migration
Keep V6/V7 and existing V8 review files intact. Add new PARTIAL_MODEL review variants with new IDs. Do not relabel existing PRODUCT_ONLY records to PARTIAL_MODEL without rewriting their full prompt. Review remains blocked pending product-specific QA. No merge or deployment.
