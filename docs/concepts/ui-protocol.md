# Charm UI Protocol Specification

## Overview

Charm Store uses a Server-Driven UI architecture.
Agents are required to return either spec-compliant JSON or standard Markdown.
Outputs are rendered into native UI components automatically by the Charm Universal Renderer.

## Output Modes

### Standard Markdown

Supports direct string streaming with rich formatting, including titles, lists, code blocks, bold/italic text, and links.

### Structured JSON

#### Viral Card

Purpose-built for sharing and revealing underlying mechanisms.

```json
// Trigger condition: JSON must include "type": "viral_card"

{
  "type": "viral_card",
  "content": {
    "cover_mode": true,        // Whether to enable the “reveal” cover mode
    "cover_data": {
      "title": "CONFIDENTIAL", // Title displayed on the cover (e.g. SECRET, TOP SECRET)
      "subtitle": "VIBE CHECK",// Subtitle displayed on the cover
      "cover_image": "https://..." // (Optional) Background image for the cover
    },
    "image_url": "https://...",    // Final result image shown after reveal (or when downloaded)
    "description": "This is your analysis result...", // Text description displayed below the card
    "action": {
      "type": "smart_share_trigger", // Fixed value, triggers native share/download logic
      "label": "REVEAL & SHARE"      // Button label
    },
    "metadata": {
      "sticker_link": "https://..."  // (Optional) Link automatically copied to clipboard when sharing (e.g. IG “Add Yours”)
    }
  }
}
```

#### Universal Timeline

Render a sequence of events as a vertical timeline.

```jsonc
// Trigger condition (heuristic detection):
// Return an Array where each object contains any of the following keywords: date, time, year, timestamp

[
  {
    "date": "2024-01-15",
    "event": "Project Kickoff",
    "description": "Initial meeting with stakeholders.",
    "location": "Taipei HQ"
  },
  {
    "date": "2024-02-01",
    "event": "Alpha Release",
    "status": "success" // Will automatically render a green check icon
  }
]

// Special style keywords:

// Content containing "error", "fail", "conflict" → Red warning style
// Content containing "success", "complete", "solve" → Green success style
// Content containing "announce", "tweet", "report" → Blue informational style
```

#### Comparison View

Render multiple objects as a responsive comparison table.

```jsonc
// Trigger condition (heuristic detection):
// Return an Array where the object keys contain comparison-related keywords: vs, competitor, price, feature, target

[
  {
    "Feature": "AI Model",
    "Charm_OS": "GPT-4o + Claude 3.5",
    "Competitor_X": "GPT-3.5"
  },
  {
    "Feature": "Viral Sharing",
    "Charm_OS": "Native Support",
    "Competitor_X": "None"
  }
]

// This array will be rendered as a responsive comparison table
```

#### Optimization Diff

Display the differences between content before and after optimization, suitable for copywriting revision or code refactoring agents.

```jsonc
// Trigger condition (heuristic detection):
// Return an Object containing keys related to both "original" and "optimized" content

// Original-related keys: original, before, weakness
// Optimized-related keys: optimized, after, rewrite

{
  "section": "Instagram Bio Rewrite",
  "original_content": "I like coffee and coding.",      // Original content
  "optimized_version": "Fueled by caffeine.\nBuilding the future of AI.\nCheck my vibe below.",  // Optimized content
  "reason": "Added emojis and line breaks for better readability." // Explanation for the optimization
}
```

#### Universal Article

Suitable for long-form content, automatically extracts headings and optimizes formatting.

```jsonc
// Trigger condition (heuristic detection):
// Return an Object containing a title (or headline) and content (or body)
// The content length must exceed 150 characters

{
  "title": "The Future of AI Agents",          // Title or headline
  "author": "Charm Intelligence",            // Optional metadata
  "body": "Artificial Intelligence is evolving from chatbots to autonomous agents...",  // Main content (long-form, >150 characters)
  "key_takeaways": [                          // Array will be automatically rendered as a list
    "Agents act autonomously",
    "Memory is crucial"
  ]
}
```

### Best Practices

- Keep JSON flat: Minimize deep nesting. The Universal Renderer performs best with flat objects.
- Use standard keywords: Since the system relies on heuristic detection, using standard English field names (e.g., date instead of d_time, title instead of header_text) ensures the correct UI is triggered.
- Mix in Markdown: You can still use Markdown syntax (e.g., Bold, Link￼) in JSON values. The renderer will parse it correctly.
