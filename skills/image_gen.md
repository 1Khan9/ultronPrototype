---
name: image_gen
type: knowledge
version: 1.0.0
description: Context for image-generation requests.
min_user_text_chars: 12
triggers:
  - make an image
  - make a picture
  - generate an image
  - generate a picture
  - draw me
  - paint me
  - create an image
  - create a picture
  - render an image
  - illustration of
  - artwork of
---

The user wants an image generated.

* Kenning's media-generation backend is local-only (ComfyUI). Paid
  cloud APIs (Fal, Runway, Suno, OpenAI image-gen, Google Imagen) are
  explicitly out of scope.
* When the request is concrete enough to dispatch ("make a picture of
  a hummingbird"), route to MEDIA_GENERATION.
* When the request is vague ("draw me something nice"), ask one
  short clarifying question — subject, style, scene.
* For requests that look like they want a real photo or screenshot,
  point the user at web image search (the APP_LAUNCH "show me a
  picture of X" path) instead of generating.
* Don't speculate about what the generated image will look like —
  describe the prompt back to the user briefly and let them refine.
